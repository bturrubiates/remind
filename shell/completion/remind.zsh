_remind_commands() {
    _commands=(
        'new:Create a new note'
        'list:List all notes'
        'edit:Edit a note'
        'find:Find a note'
        'delete:Delete a note'
    )

    _describe 'subcommand' _commands
}

_remind_list_notes() {
    _notes=($(remind list --name-only))
    _describe 'notes' _notes
}

_remind() {
    local context state state_descr line
    typeset -A opt_args

    _arguments '1: :_remind_commands' \
               '*::arg:->args'

    case "$line[1]" in
        list)
            _arguments '--name-only[Name only]' \
                       '--decorate[Decorate]'
        ;;
        edit)
            _arguments '1: :_remind_list_notes'
        ;;
        find)
            _arguments '1: :_remind_list_notes'
        ;;
        delete)
            _arguments '1: :_remind_list_notes'
        ;;
    esac
}

compdef _remind remind
