#!/bin/sh
set -eu

canonical_release_base="https://github.com/marcos-guilherme/socratic-learn/releases/latest/download"
canonical_manifest_url="https://github.com/marcos-guilherme/socratic-learn/releases/latest/download/release-manifest.json"
release_base=${SOCRATIC_RELEASE_BASE_URL:-$canonical_release_base}

system_name=$(uname -s)
case "$system_name" in
    Linux) platform=linux ;;
    Darwin) platform=macos ;;
    *)
        printf '%s\n' "Unsupported operating system. Fallback: pipx install socratic-learn" >&2
        exit 1
        ;;
esac

machine=$(uname -m)
case "$machine" in
    x86_64) ;;
    *)
        printf '%s\n' "Only x86-64 is supported. Fallback: pipx install socratic-learn" >&2
        exit 1
        ;;
esac

printf '%s\n' "Warning: this release is unsigned and macOS Gatekeeper may warn before it runs." >&2
if [ "${SOCRATIC_INSTALL_YES:-0}" != "1" ]; then
    printf '%s' "Continue with the download? [y/N] " >&2
    IFS= read -r confirmation || confirmation=
    case "$confirmation" in
        y|Y|yes|YES|Yes) ;;
        *)
            printf '%s\n' "Installation cancelled. Fallback: pipx install socratic-learn" >&2
            exit 1
            ;;
    esac
fi

validate_loopback_url() {
    candidate=$1
    case "$candidate" in
        *'#'*|*'?'*|*'@'*) return 1 ;;
        http://*) ;;
        *) return 1 ;;
    esac
    remainder=${candidate#http://}
    authority=${remainder%%/*}
    case "$authority" in
        localhost|127.0.0.1|'[::1]')
            return 0
            ;;
        localhost:*|127.0.0.1:*)
            port=${authority#*:}
            ;;
        '[::1]':*)
            port=${authority#'[::1]:'}
            ;;
        *)
            return 1
            ;;
    esac
    case "$port" in
        ''|*[!0-9]*) return 1 ;;
        *)
            if [ "${#port}" -gt 5 ] || [ "$port" -gt 65535 ]; then
                return 1
            fi
            return 0
            ;;
    esac
}

validate_https_url() {
    candidate=$1
    case "$candidate" in
        *'#'*|*'@'*) return 1 ;;
        https://*) ;;
        *) return 1 ;;
    esac
    remainder=${candidate#https://}
    authority=${remainder%%/*}
    case "$authority" in
        ''|*'?'*) return 1 ;;
        *) return 0 ;;
    esac
}

if [ "$release_base" = "$canonical_release_base" ]; then
    trust_mode=production
elif validate_loopback_url "$release_base"; then
    trust_mode=loopback
else
    printf '%s\n' "Release URL is outside the trusted download boundary." >&2
    exit 1
fi

release_base=${release_base%/}
asset="socratic-${platform}-x86_64"
install_dir=${SOCRATIC_INSTALL_DIR:-${XDG_BIN_HOME:-"$HOME/.local/bin"}}
channel_home=${SOCRATIC_LEARN_HOME:-"$HOME/.socratic-learn"}

mkdir -p "$install_dir" "$channel_home"
install_dir=$(cd "$install_dir" && pwd -P)
channel_home=$(cd "$channel_home" && pwd -P)
target="$install_dir/socratic"
staged="$install_dir/socratic.new"
checksums="$install_dir/SHA256SUMS.new"
channel_target="$channel_home/channel.json"
channel_staged="$channel_home/channel.json.new"

cleanup() {
    rm -f \
        "$staged" "$checksums" "$channel_staged" \
        "$staged.part" "$staged.headers" \
        "$checksums.part" "$checksums.headers"
}
trap cleanup EXIT HUP INT TERM

curl_download() {
    current_url=$1
    destination=$2
    response_body="$destination.part"
    response_headers="$destination.headers"
    redirect_count=0
    while [ "$redirect_count" -le 10 ]; do
        rm -f "$response_body" "$response_headers"
        if [ "$trust_mode" = production ]; then
            validate_https_url "$current_url" || {
                printf '%s\n' "Redirect left the trusted HTTPS boundary." >&2
                return 1
            }
            status=$(
                curl --fail --silent --show-error \
                    --proto '=https' --proto-redir '=https' --tlsv1.2 \
                    --max-redirs 0 --dump-header "$response_headers" \
                    --output "$response_body" --write-out '%{http_code}' \
                    "$current_url"
            ) || return 1
        else
            validate_loopback_url "$current_url" || {
                printf '%s\n' "Redirect left the trusted loopback boundary." >&2
                return 1
            }
            status=$(
                curl --fail --silent --show-error \
                    --proto '=http' --proto-redir '=http' \
                    --max-redirs 0 --dump-header "$response_headers" \
                    --output "$response_body" --write-out '%{http_code}' \
                    "$current_url"
            ) || return 1
        fi
        case "$status" in
            2??)
                mv "$response_body" "$destination"
                rm -f "$response_headers"
                return 0
                ;;
            3??)
                locations=$(
                    awk '
                        tolower(substr($0, 1, 9)) == "location:" {
                            sub(/^[^:]*:[ \t]*/, "")
                            sub(/\r$/, "")
                            print
                        }
                    ' "$response_headers"
                )
                location_count=$(
                    printf '%s\n' "$locations" |
                        awk 'NF {count++} END {print count + 0}'
                )
                if [ "$location_count" -ne 1 ]; then
                    printf '%s\n' "Redirect must contain one trusted Location." >&2
                    return 1
                fi
                current_url=$locations
                redirect_count=$((redirect_count + 1))
                ;;
            *)
                printf '%s\n' "Release download returned HTTP $status." >&2
                return 1
                ;;
        esac
    done
    printf '%s\n' "Release download exceeded the trusted redirect limit." >&2
    return 1
}

curl_download "$release_base/SHA256SUMS" "$checksums"
curl_download "$release_base/$asset" "$staged"

matches=$(awk -v name="$asset" '$2 == name {print $1}' "$checksums")
match_count=$(printf '%s\n' "$matches" | awk 'NF {count++} END {print count + 0}')
if [ "$match_count" -ne 1 ]; then
    printf '%s\n' "SHA256SUMS must contain exactly one entry for $asset." >&2
    exit 1
fi
expected_hash=$matches
case "$expected_hash" in
    *[!0-9a-f]*|'')
        printf '%s\n' "SHA256SUMS contains an invalid SHA-256 digest for $asset." >&2
        exit 1
        ;;
esac
if [ "${#expected_hash}" -ne 64 ]; then
    printf '%s\n' "SHA256SUMS contains an invalid SHA-256 digest for $asset." >&2
    exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
    actual_hash=$(sha256sum <"$staged" | awk '{print $1}')
elif command -v shasum >/dev/null 2>&1; then
    actual_hash=$(shasum -a 256 <"$staged" | awk '{print $1}')
else
    printf '%s\n' "A SHA-256 utility is required (sha256sum or shasum)." >&2
    exit 1
fi
if [ "$actual_hash" != "$expected_hash" ]; then
    printf '%s\n' "Release artifact SHA-256 mismatch." >&2
    exit 1
fi

json_escape() {
    LC_ALL=C awk '
        BEGIN { ORS = "" }
        {
            if (NR > 1) {
                printf "\\n"
            }
            gsub(/\\/, "\\\\")
            gsub(/"/, "\\\"")
            gsub(/\r/, "\\r")
            gsub(/\t/, "\\t")
            printf "%s", $0
        }
    '
}

shell_single_quote() {
    LC_ALL=C awk '
        BEGIN {
            ORS = ""
            printf "\047"
        }
        {
            if (NR > 1) {
                printf "\\n"
            }
            gsub(/\047/, "\047\\\047\047")
            printf "%s", $0
        }
        END {
            printf "\047"
        }
    '
}

escaped_target=$(printf '%s' "$target" | json_escape)
escaped_manifest=$(printf '%s' "$canonical_manifest_url" | json_escape)
umask 077
cat >"$channel_staged" <<EOF
{
  "schema_version": 1,
  "channel": "native",
  "executable": "$escaped_target",
  "manifest_url": "$escaped_manifest"
}
EOF

chmod 755 "$staged"
mv "$channel_staged" "$channel_target"
mv "$staged" "$target"

case ":${PATH:-}:" in
    *":$install_dir:"*) ;;
    *)
        quoted_install_dir=$(printf '%s' "$install_dir" | shell_single_quote)
        printf 'export PATH=%s:"$PATH"\n' "$quoted_install_dir"
        ;;
esac
printf '%s\n' "Run: socratic"
