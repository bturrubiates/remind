# remind

Remind is a quick tool to easily take and manage meeting notes.

If there is a Git installation available on in the `$PATH`, then `remind` will
attempt to enable Git support. It does not use a wrapper like `libgit2`, it
shells out to the system Git installation. The Git support allows `remind` to
commit notes after they are written edited and remove them from the repository
when they are deleted.

## Installing

At the moment, this is simply a single Python script. It requires Python 3 to
work, but that's about it. Put it somewhere in the `$PATH`.

## Configuration

Right now there are three environment variables that are read by `remind`:

* `REMIND_GIT_DISABLE`: If set, disable Git support.
* `REMIND_NOTES_DIR`: If set, use this as the top-level directory for notes.
* `EDITOR`: Standard environment variable that stores the command to run for
            the users preferred editor.

There is also a script in the `shell` directory called `fremind`. This is a
script that uses [fzf](https://github.com/junegunn/fzf), to provide a nice
interface to the tool.

## Usage

### remind

* Create a new note, and optionally track it in Git:

  ```sh
  remind new <note name>
  ```
* Edit a note, and optionally commit the edit:

  ```sh
  remind edit <note name>
  ```
* Delete a note, and optionally remove it from Git tracking:

  ```sh
  remind delete <note name>
  ```
* List all notes:

  ```sh
  remind list
  ```

  The notes are organized by date, to only list names:

  ```sh
  remind list --name-only
  ```

  To show extra Git information, use `--decorate`:

  ```sh
  remind list --decorate
  remind list --decorate --name-only
  ```

  If Git is disabled, or no Git is available, then output will be as if
  `--decorate` had not been specified at all.
* Find the full path to a note:

  ```sh
  remind find <note name>
  ```

### fremind

By default, running `fremind` will bring up a list of the named notes that is
searchable using the fuzzy finding facilities provided by `fzf`. Optionally, a
starting query can be provided as an argument to fremind to narrow down the
notes selection.

Hitting enter on a note will run `remind edit`, and hitting the delete key on a
note will run `remind delete`. The user will be prompted before deletion for
safety.

## Completions

A completion script is available in `shell/completion` that can be used with
`zsh` to provide autocompletion.

Download the `shell/completion/remind.zsh` script and source it in your
`~/.zshrc`.
