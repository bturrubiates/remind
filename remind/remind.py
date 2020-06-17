#!/usr/bin/env python3

import subprocess
import datetime
import argparse
import shutil
import shlex
import errno
import sys
import re
import os

TLD_ENV_NAME = "REMIND_NOTES_DIR"
TLD_DEFAULT = "~/meeting-notes/"

GIT_DISABLE_ENV_NAME = "REMIND_GIT_DISABLE"

TEMPLATE_DIR = "REMIND_TEMPLATE_DIR"

EDITOR_ENV_NAME = "EDITOR"
EDITOR_DEFAULT = "vim"

###############################################################################


def prompt(message, prefix=">>"):
    return input(
        "{prefix} {message}\n{prefix} ".format(prefix=prefix, message=message)
    ).strip()


def yesno(message, default="yes"):
    if default != "yes" and default != "no":
        raise ValueError("default must be yes/no")

    response = prompt("{} [{}]".format(message, default))
    while True:
        if response == "":
            return True

        if re.match("^(y)(es)?", response, re.IGNORECASE):
            return default == "yes"
        elif re.match("^(n)(o)?", response, re.IGNORECASE):
            return default == "no"

        response = prompt("{} [{}]".format(message, default))


def git_prompt_commit(note):
    return yesno("Git commit the note {}?".format(note))


def git_prompt_delete(target):
    if isinstance(target, Note):
        description = "note"
    else:
        description = "notebook"

    return yesno(
        "Git rm the {description} {target}?".format(
            description=description, target=target
        )
    )

def prompt_create_directory(directory):
    return yesno("{} does not exist, create?".format(directory))


def check_directory(directory):
    return os.path.exists(directory)


def create_directory(directory):
    if prompt_create_directory(directory):
        os.makedirs(directory, exist_ok=True)
        return True

    return False

def get_and_verify_tld():
    tld = os.path.expanduser(os.environ.get(TLD_ENV_NAME, TLD_DEFAULT))
    exists = check_directory(tld)
    if not exists and not create_directory(tld):
        print("Cannot continue without top-level notes directory",
              file=sys.stderr)
        sys.exit(1)

    return tld


def get_git_config(tld):
    disabled = int(os.environ.get(GIT_DISABLE_ENV_NAME, 0)) == 1
    if disabled:
        return None

    try:
        git = Git(tld)
    except RuntimeError:
        print(
            "No usable Git implementation found, continuing without it.",
            file=sys.stderr,
        )
        return None

    if not git.is_initialized:
        init = yesno("Do you want to initialize git for {}?".format(tld))
        if not init:
            return None

        git.initialize()

    return git


def find_note(tld, note, notebook=None):
    if notebook:
        return Notebook(tld, notebook).find(note)
    elif '/' in note:
        # Try to handle both full paths, and relative paths. Use rsplit to
        # split from the right side, max of two. Then take the last two items
        # of the list. This will crash if the note is malformed, but oh well.
        # We trust our callers here!
        notebook, note = note.rsplit('/', 2)[-2:]

    matches = Notebook.search(tld, note)
    if not matches:
        print("Found no match for {note}".format(note=note), file=sys.stderr)
        sys.exit(1)
    elif len(matches) > 1:
        print(
            "Found more than one match, specify notebook to disambiguate.",
            file=sys.stderr,
        )
        sys.exit(1)

    return matches[0]


###############################################################################


class Template:
    def __init__(self, notebook, prompt_create=False):
        self.tld = notebook.tld
        self.notebook = notebook

        self.dir = os.environ.get(
            TEMPLATE_DIR, os.path.join(self.tld, "templates")
        )

        self._prompt_create = prompt_create
        self._resolved = False
        self._template = None
        self._runner = None


    def _resolve(self):
        configured = self._configure(self.notebook.name)
        if not configured and self._prompt_create and self.create():
            configured = self._configure(self.notebook.name)

        if not configured:
            self._configure("default")

        self._resolved = True

    def _configure(self, notebook):
        ntd = os.path.join(self.dir, notebook)
        template = os.path.join(ntd, "{}.txt".format(notebook))
        runnable = os.path.join(ntd, "{}.py".format(notebook))

        if os.path.isfile(template) and os.path.isfile(runnable):
            with open(template, "r") as f:
                self._template = f.read()

            import importlib.util

            spec = importlib.util.spec_from_file_location(notebook, runnable)
            self._runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self._runner)

            return True

        return False

    def _tokenize(self):
        if self._template:
            return re.split("({{[\s\w]*}})", self._template)

        return []

    def render(self, note):
        out = []

        if not self._resolved:
            self._resolve()

        for token in self._tokenize():
            try:
                if token.startswith("{{"):
                    fn = token[2:-2].strip()
                    token = getattr(self._runner, fn)(self.notebook, note.name)
            except:
                pass

            out.append(token)

        return "".join(out)

    def create(self):
        if not yesno("Do you want to create a template?"):
            return False

        ntd = os.path.join(self.dir, self.notebook.name)
        if not check_directory(ntd) and not create_directory(ntd):
            return False

        template = os.path.join(ntd, "{}.txt".format(self.notebook))
        runnable = os.path.join(ntd, "{}.py".format(self.notebook))

        editor = os.environ.get(EDITOR_ENV_NAME, EDITOR_DEFAULT)
        subprocess.call([editor, template, runnable])


    def delete(self):
        ntd = os.path.join(self.dir, self.notebook.name)
        if check_directory(ntd):
            delete = yesno(
                "Do you want to delete the template for {notebook}".format(
                    notebook=self.notebook.name))
            if delete:
                shutil.rmtree(ntd)

class Note:
    def __init__(self, notebook, name):
        self.name = name
        self.notebook = notebook

        self.path = os.path.join(notebook.path, self.name)

    def exists(self):
        return os.path.isfile(self.path)

    def edit(self):
        editor = os.environ.get(EDITOR_ENV_NAME, EDITOR_DEFAULT)
        subprocess.call([editor, self.path])

    def prepopulate(self):
        template = self.notebook.template
        with open(self.path, "w+") as f:
            f.write(template.render(self))

    def delete(self):
        os.remove(self.path)

    def __str__(self):
        return self.name


class Notebook:
    def __init__(self, tld, notebook, prompt_create=False):
        self.tld = tld
        self.name = notebook
        self.path = os.path.join(tld, notebook)

        self._template = None
        self._assert_existence(prompt_create)


    def _assert_existence(self, prompt_create):
        if check_directory(self.path):
            return

        if prompt_create:
            if not create_directory(self.path):
                print("Cannot continue without creating {notebook}".format(
                    notebook=self.name), file=sys.stderr)
                sys.exit(1)
            else:
                self._template = Template(self, prompt_create=True)
        else:
            print("Notebook {notebook} does not exist".format(
                notebook=self.name), file=sys.stderr)
            sys.exit(1)

    @property
    def template(self):
        if not self._template:
            self._template = Template(self)

        return self._template

    def sift(self):
        return [Note(self, f) for f in sorted(os.listdir(self.path))]

    def find(self, note):
        path = os.path.join(self.path, note)
        if os.path.isfile(path):
            return Note(self, note)

        return None

    def empty(self):
        return not os.listdir(self.path)

    def delete(self):
        shutil.rmtree(self.path)
        self.template.delete()

    @classmethod
    def search(cls, tld, note):
        matches = []

        for notebook in cls.discover(tld):
            match = notebook.find(note)
            if match:
                matches.append(match)

        return matches

    @classmethod
    def discover(cls, tld, filt=None):
        notebooks = []

        for d in os.listdir(tld):
            if not os.path.isdir(os.path.join(tld, d)):
                continue

            if d.startswith(".") or d == "templates":
                continue

            if not filt or filt(d):
                notebooks.append(Notebook(tld, d))

        return notebooks

    def __str__(self):
        return self.name


class Git:
    def __init__(self, tld):
        self.tld = tld
        self.path = shutil.which("git")
        if not self.path:
            raise RuntimeError("Unable to find usable Git executable")

        self._tracked = None

    def _format_cmd(self, command):
        return shlex.split("{} {}".format(self.path, command))

    def _run(self, command, **kwargs):
        return subprocess.Popen(
            self._format_cmd(command), cwd=self.tld, **kwargs
        )

    def _run_silent(self, command):
        context = self._run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return context.wait()

    def _run_capture(self, command):
        context = self._run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return context.communicate()

    def add(self, filename):
        relpath = os.path.relpath(filename, self.tld)
        return self._run_silent("add {}".format(relpath))

    def rm(self, filename, recursive=False):
        relpath = os.path.relpath(filename, self.tld)
        if recursive:
            fmt = "rm -r {}"
        else:
            fmt = "rm {}"

        return self._run_silent(fmt.format(relpath))

    def commit(self):
        context = self._run("commit")
        context.wait()

    def initialize(self):
        return self._run_silent("init")

    def is_tracked(self, path):
        relpath = os.path.relpath(path, self.tld)
        paths, _ = self._run_capture("ls-files {}".format(relpath))
        return len(paths) != 0

    def is_modified(self, filename):
        relpath = os.path.relpath(filename, self.tld)
        return self._run_silent(
            "diff --exit-code --name-only {}".format(relpath)
        )

    @property
    def is_initialized(self):
        return self._run_silent("rev-parse --git-dir") == 0


###############################################################################


def command_new(args, tld):
    git = get_git_config(tld)

    notebook = Notebook(tld, args.notebook, prompt_create=True)
    note = Note(notebook, args.note)
    if note.exists():
        print("Note already exists, use edit.", file=sys.stderr)
        sys.exit(1)

    note.prepopulate()
    note.edit()

    if git and git_prompt_commit(note.path):
        git.add(note.path)
        git.commit()

def _delete_note(args, tld, git, notebook):
    note = notebook.find(args.note)
    if not note:
        print("Unable to find note")
        sys.exit(1)

    delete = yesno(
        "Are you sure you want to delete the note {}".format(note)
    )
    if not delete:
        return

    note.delete()
    if note.notebook.empty():
        note.notebook.delete()

    if git and git.is_tracked(note.path) and git_prompt_delete(note):
        git.rm(note.path)
        git.commit()

def _delete_notebook(args, tld, git, notebook):
    delete = yesno(
        "Are you sure you want to delete the notebook {}".format(notebook)
    )
    if not delete:
        return

    notebook.delete()
    if (
        git
        and git.is_tracked(notebook.path)
        and git_prompt_delete(notebook)
    ):
        git.rm(notebook.path, recursive=True)
        git.commit()

def command_delete(args, tld):
    git = get_git_config(tld)
    notebook = Notebook(tld, args.notebook)

    if args.note:
        _delete_note(args, tld, git, notebook)
    else:
        _delete_notebook(args, tld, git, notebook)


def command_list(args, tld):
    def filter_by_name(candidate):
        name = args.notebook

        return not name or (candidate == name)

    git = get_git_config(tld)

    notebooks = Notebook.discover(tld, filt=filter_by_name)
    if not notebooks:
        sys.exit(1)

    n_notebooks = len(notebooks)
    for i, notebook in enumerate(notebooks):
        if not args.oneline:
            print("{notebook}/".format(notebook=notebook))
        for note in notebook.sift():
            if args.decorate:
                if git and git.is_tracked(note.path):
                    decoration = "[t] "
                else:
                    decoration = "[u] "
            else:
                decoration = ""

            if args.oneline:
                print("{decoration}{notebook}/{note}".format(
                    decoration=decoration, notebook=notebook, note=note))
            else:
                print(
                    "  * {decoration}{note}".format(
                        decoration=decoration, note=note
                    )
                )

        if not args.oneline and i != n_notebooks - 1:
            print()


def command_edit(args, tld):
    git = get_git_config(tld)
    note = find_note(tld, args.note, args.notebook)
    if not note:
        print("Unable to find note")
        sys.exit(1)

    note.edit()

    path = note.path
    if git and git.is_modified(path) and git_prompt_commit(note):
        git.add(path)
        git.commit()


def command_find(args, tld):
    note = find_note(tld, args.note, args.notebook)
    if not note:
        print("Unable to find note")
        sys.exit(1)

    print(note.path)

def command_info(args, tld):
    print("PATH:{tld}".format(tld=tld))


###############################################################################


def parse_arguments():
    description = "A script to manage meeting notes"

    parser = argparse.ArgumentParser(description=description)
    sub = parser.add_subparsers(help="commands", dest='cmd')
    sub.required = True

    n_req_parser = argparse.ArgumentParser(add_help=False)
    n_req_parser.add_argument("note", help="Name of note")

    n_opt_parser = argparse.ArgumentParser(add_help=False)
    n_opt_parser.add_argument(
        "note", help="Name of note", default=None, nargs="?"
    )

    nb_req_parser = argparse.ArgumentParser(add_help=False)
    nb_req_parser.add_argument("notebook", help="Name of notebook")

    nb_opt_parser = argparse.ArgumentParser(add_help=False)
    nb_opt_parser.add_argument(
        "notebook", help="Name of notebook", default=None, nargs="?"
    )

    n = sub.add_parser(
        "new", help="Create a new note", parents=[nb_req_parser, n_req_parser]
    )
    n.set_defaults(command=command_new)

    d = sub.add_parser(
        "delete", help="Delete a note", parents=[nb_req_parser, n_opt_parser]
    )
    d.set_defaults(command=command_delete)

    l = sub.add_parser("list", help="List notes", parents=[nb_opt_parser])
    l.set_defaults(command=command_list)
    l.add_argument(
        "--decorate", help="Include Git tracking info", action="store_true"
    )
    l.add_argument(
        "--oneline",
        help="Print each note on it's own line",
        action="store_true"
    )

    e = sub.add_parser(
        "edit", help="Edit a note", parents=[nb_opt_parser, n_req_parser]
    )
    e.set_defaults(command=command_edit)

    f = sub.add_parser(
        "find",
        help="Find note path by name",
        parents=[nb_opt_parser, n_req_parser],
    )
    f.set_defaults(command=command_find)

    i = sub.add_parser(
        "info",
        help="Print info about remind",
    )
    i.set_defaults(command=command_info)

    return parser.parse_args()


def main():
    tld = get_and_verify_tld()
    args = parse_arguments()
    args.command(args, tld)


if __name__ == "__main__":
    exit(main())
