#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
managed_block_begin='<!-- BEGIN CODEX PRO WORKFLOW -->'
managed_block_end='<!-- END CODEX PRO WORKFLOW -->'
utf8_bom=$(printf '\357\273\277')

cat <<'BANNER'
+---------------------------------------+
|    _    ____ _____ ____      _        |
|   / \  / ___|_   _|  _ \    / \       |
|  / _ \ \___ \ | | | |_) |  / _ \      |
| / ___ \ ___) || | |  _ <  / ___ \     |
|/_/   \_\____/ |_| |_| \_\/_/   \_\    |
|                                       |
|       O R C H E S T R A T O R         |
|    Plan and orchestrate with Sol.     |
|    Execute with Luna High/Max.        |
+---------------------------------------+
BANNER
printf '%s\n' 'Interactive project setup'
printf '%s' 'Target repository path: '
IFS= read -r target_path || exit 1

if [ -z "$target_path" ] || [ ! -d "$target_path" ]; then
    printf 'Error: target must be an existing directory: %s\n' "${target_path:-<empty>}" >&2
    exit 1
fi

target_dir=$(CDPATH= cd -- "$target_path" && pwd -P)
if [ "$target_dir" = "$script_dir" ]; then
    printf 'Error: target repository must be different from the setup source directory.\n' >&2
    exit 1
fi

confirm() {
    prompt=$1
    default_yes=$2
    if [ "$default_yes" = yes ]; then
        suffix='[Y/n]'
    else
        suffix='[y/N]'
    fi

    while :; do
        printf '%s %s ' "$prompt" "$suffix"
        if ! IFS= read -r answer; then
            printf '\nSetup cancelled: input ended before setup was complete.\n' >&2
            exit 1
        fi

        case "$answer" in
            y|Y|yes|YES|Yes) return 0 ;;
            n|N|no|NO|No) return 1 ;;
            '') [ "$default_yes" = yes ] && return 0 || return 1 ;;
            *) printf '%s\n' 'Please answer yes or no.' ;;
        esac
    done
}

overwrite_paths() {
    source_path=$1
    destination_path=$2
    component_name=$(basename "$source_path")

    if [ -f "$source_path" ]; then
        if [ -e "$destination_path" ] || [ -L "$destination_path" ]; then
            printf '%s\n' "$component_name"
        else
            return
        fi
        return
    fi

    find "$source_path" -type f -print | while IFS= read -r source_file; do
        relative_path=${source_file#"$source_path"/}
        destination_file=$destination_path/$relative_path
        if [ -e "$destination_file" ] || [ -L "$destination_file" ]; then
            printf '%s\n' "$component_name/$relative_path"
        fi
    done
}

print_overwrites() {
    source_path=$1
    destination_path=$2

    overwrite_list=$(overwrite_paths "$source_path" "$destination_path")
    if [ -z "$overwrite_list" ]; then
        return
    fi

    printf '%s\n' 'WARNING: the following existing files will be overwritten:'
    printf '%s\n' "$overwrite_list" | sed 's/^/  - /'
}

merge_conflicts() {
    source_path=$1
    destination_path=$2

    find "$source_path" -type f -print | while IFS= read -r source_file; do
        relative_path=${source_file#"$source_path"/}
        destination_file=$destination_path/$relative_path
        if { [ -e "$destination_file" ] || [ -L "$destination_file" ]; } && [ ! -f "$destination_file" ]; then
            printf '%s\n' "$relative_path"
        fi
    done

    find "$source_path" -type d -print | while IFS= read -r source_directory; do
        if [ "$source_directory" = "$source_path" ]; then
            continue
        fi
        relative_path=${source_directory#"$source_path"/}
        destination_directory=$destination_path/$relative_path
        if { [ -e "$destination_directory" ] || [ -L "$destination_directory" ]; } && [ ! -d "$destination_directory" ]; then
            printf '%s\n' "$relative_path"
        fi
    done
}

select_plan() {
    printf '%s\n' 'Choose Profile to install'
    printf '%s\n' '  1) Pro - Sol plans/solves, Luna High/Max handles routine work, Astra reviews'
    printf '%s\n' '  2) Pro (max 2 subagents) - same roles, with at most 2 concurrent subagents'

    while :; do
        printf '%s' 'Select profile [1-2] (default 1): '
        if ! IFS= read -r answer; then
            printf '\nSetup cancelled: input ended before setup was complete.\n' >&2
            exit 1
        fi

        case "$answer" in
            1|pro|PRO|Pro|'') plan=pro; return ;;
            2|pro-max-2-subagents) plan=pro-max-2-subagents; return ;;
            *) printf '%s\n' 'Please enter a listed profile number or name.' ;;
        esac
    done
}

copy_component() {
    name=$1
    source_path=${2:-$script_dir/$name}
    destination_path=$target_dir/$name
    component_installed=no

    if [ ! -e "$source_path" ]; then
        printf 'Error: setup source is missing: %s\n' "$source_path" >&2
        exit 1
    fi

    if [ -e "$destination_path" ] || [ -L "$destination_path" ]; then
        if [ "$name" = AGENTS.md ]; then
            if [ -L "$destination_path" ] || [ ! -f "$destination_path" ]; then
                printf 'Skipped %s: target must be a regular file, not a symbolic link.\n' "$name" >&2
                return 0
            fi
            if ! managed_block=$(awk \
                -v begin="$managed_block_begin" \
                -v end="$managed_block_end" \
                -v bom="$utf8_bom" '
                {
                    line = $0
                    sub(/\r$/, "", line)
                    if (FNR == 1 && substr(line, 1, length(bom)) == bom) {
                        line = substr(line, length(bom) + 1)
                    }
                    if (line == begin) {
                        begin_count++
                        if (capture) invalid = 1
                        capture = 1
                    }
                    if (capture) print line
                    if (line == end) {
                        end_count++
                        if (!capture) invalid = 1
                        else complete_count++
                        capture = 0
                    }
                }
                END {
                    if (begin_count != 1 || end_count != 1 ||
                        complete_count != 1 || capture || invalid) exit 42
                }
            ' "$source_path"); then
                printf '%s\n' 'Error: setup AGENTS.md must contain exactly one valid managed workflow block.' >&2
                exit 1
            fi
            if [ -z "$managed_block" ]; then
                printf '%s\n' 'Error: setup AGENTS.md managed workflow block extraction was empty.' >&2
                exit 1
            fi

            if grep -Fq "$managed_block_begin" "$destination_path" || grep -Fq "$managed_block_end" "$destination_path"; then
                temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/codex-pro-setup.XXXXXX")
                block_file=$temp_dir/managed-block
                updated_file=$temp_dir/AGENTS.md
                printf '%s\n' "$managed_block" > "$block_file"
                if ! awk \
                    -v begin="$managed_block_begin" \
                    -v end="$managed_block_end" \
                    -v bom="$utf8_bom" '
                    FNR == NR {
                        block_lf = block_lf $0 ORS
                        block_crlf = block_crlf $0 "\r\n"
                        next
                    }
                    {
                        line = $0
                        marker_uses_crlf = sub(/\r$/, "", line)
                        target_has_bom = (FNR == 1 && substr(line, 1, length(bom)) == bom)
                        if (target_has_bom) line = substr(line, length(bom) + 1)

                        if (line == begin) {
                            begin_count++
                            if (replacing) invalid = 1
                            if (target_has_bom) printf "%s", bom
                            if (marker_uses_crlf) printf "%s", block_crlf
                            else printf "%s", block_lf
                            replacing = 1
                            next
                        }
                        if (line == end) {
                            end_count++
                            if (!replacing) invalid = 1
                            replacing = 0
                            next
                        }
                        if (!replacing) print $0
                    }
                    END {
                        if (begin_count != 1 || end_count != 1 || replacing || invalid) exit 42
                    }
                ' "$block_file" "$destination_path" > "$updated_file"; then
                    rm -- "$block_file" "$updated_file"
                    rmdir -- "$temp_dir"
                    printf '%s\n' 'Error: target AGENTS.md has malformed, duplicate, or out-of-order managed workflow markers; left it unchanged.' >&2
                    exit 1
                fi
                if cmp -s "$updated_file" "$destination_path"; then
                    printf 'Skipped %s: managed workflow block already current.\n' "$name"
                    rm -- "$block_file" "$updated_file"
                    rmdir -- "$temp_dir"
                    return 0
                fi
                cp "$updated_file" "$destination_path"
                rm -- "$block_file" "$updated_file"
                rmdir -- "$temp_dir"
                printf 'Updated managed workflow block in %s. Unrelated contents preserved.\n' "$name"
                component_installed=yes
                return 0
            fi

            if grep -Eqi 'astra-orchestrator|Sol root|Astra reviewer|Luna (High|Max)' "$destination_path"; then
                printf '%s\n' 'WARNING: legacy unmarked orchestrator instructions were preserved in AGENTS.md; review/remove them manually to avoid conflicting rules.' >&2
            fi
            printf '\n\n%s\n' "$managed_block" >> "$destination_path"
            printf 'Appended managed workflow block to %s. Existing contents preserved.\n' "$name"
            component_installed=yes
            return 0
        fi
        if [ ! -L "$destination_path" ] && [ -d "$source_path" ] && [ -d "$destination_path" ]; then
            linked_path=$(find "$destination_path" -type l -print -quit)
            if [ -n "$linked_path" ]; then
                printf 'Skipped %s: the existing target contains a symbolic link (%s).\n' \
                    "$name" "$linked_path" >&2
                return 0
            fi
            conflict_list=$(merge_conflicts "$source_path" "$destination_path")
            if [ -n "$conflict_list" ]; then
                printf 'Skipped %s: source and target types conflict at:\n' "$name" >&2
                printf '%s\n' "$conflict_list" | sed 's/^/  /' >&2
                return 0
            fi
        elif [ ! -L "$destination_path" ] && { [ -d "$source_path" ] && [ ! -d "$destination_path" ] || [ -f "$source_path" ] && [ ! -f "$destination_path" ]; }; then
            printf 'Skipped %s: source and target types are incompatible.\n' "$name" >&2
            return 0
        fi

        if [ -L "$destination_path" ]; then
            printf '%s\n' 'WARNING: the following symbolic link will be replaced:'
            printf '  - %s\n' "$name"
        else
            print_overwrites "$source_path" "$destination_path"
        fi
        if ! confirm "Update $name? New files will be added; only paths listed above will be replaced." no; then
            printf 'Skipped %s (existing target left unchanged).\n' "$name"
            return 0
        fi

        if [ -L "$destination_path" ]; then
            rm "$destination_path"
            cp -R "$source_path" "$destination_path"
        elif [ -d "$source_path" ] && [ -d "$destination_path" ]; then
            cp -R "$source_path"/. "$destination_path"/
        elif [ -f "$source_path" ] && [ -f "$destination_path" ]; then
            cp "$source_path" "$destination_path"
        fi
        printf 'Updated %s.\n' "$name"
    else
        cp -R "$source_path" "$destination_path"
        printf 'Installed %s.\n' "$name"
    fi
    component_installed=yes
}

remove_legacy_deepseek_files() {
    codex_dir=$target_dir/.codex
    legacy_files=''
    for name in \
        local_deepseek_runner.py \
        models.json \
        run-deepseek-role.ps1 \
        start-ustc-adapter.ps1 \
        start-ustc-adapter.sh \
        ustc_chat_adapter.py
    do
        path=$codex_dir/$name
        if [ -f "$path" ]; then
            if [ "$name" != models.json ] || grep -qi 'deepseek-' "$path"; then
                legacy_files="$legacy_files
$path"
            fi
        fi
    done
    if [ -z "$legacy_files" ]; then
        return
    fi

    printf '%s\n' 'The following obsolete DeepSeek adapter files remain from an older profile:'
    printf '%s\n' "$legacy_files" | sed '/^$/d; s/^/  - /'
    if ! confirm 'Remove these obsolete files?' yes; then
        printf '%s\n' 'Left obsolete adapter files unchanged.'
        return
    fi
    printf '%s\n' "$legacy_files" | while IFS= read -r path; do
        if [ -n "$path" ]; then
            rm -- "$path"
        fi
    done
    printf '%s\n' 'Removed obsolete DeepSeek adapter files.'
}

plan=pro
select_plan

installed=0
for component in .codex .agents AGENTS.md; do
    if confirm "Install $component?" yes; then
        if [ "$component" = .codex ]; then
            copy_component "$component" "$script_dir/profiles/$plan/codex"
        elif [ "$component" = .agents ]; then
            copy_component "$component" "$script_dir/profiles/$plan/agents"
        else
            copy_component "$component"
        fi
        if [ "$component_installed" = yes ]; then
            installed=$((installed + 1))
            if [ "$component" = .codex ]; then
                remove_legacy_deepseek_files
            fi
        fi
    else
        printf 'Skipped %s.\n' "$component"
    fi
done

printf '\nSetup complete. %s component(s) installed in %s (profile: %s).\n' "$installed" "$target_dir" "$plan"
printf '%s\n' 'See guides/ for optional Codex model and Fast-mode configurations.'
