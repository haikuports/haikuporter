#!/bin/bash
die() {
	printf %s "${@+$@$'\n'}"
	exit 1
}

usage() {
	cat <<- EOF
	Usage: ./generate-crates.io-dependencies.sh [options] portname

	Outputs the SOURCE_URI's and CHECKSUM_SHA256's of a Rust package's
	dependencies from crates.io.

	Options:
	  -h, --help	show this help message and exit
	  -k, --keep	keep the generated temporary directory
	  -psd, --print-source-directories
	 		Also print SOURCE_DIR's
	  -d DIR, --directory=DIR
	 		specify the port directory
	EOF
}
keep() { rm -rf "$tempdir"; }

psd=2
args=1
while (( args > 0 )); do
	case "$1" in
		""|-h|--help )
			usage
			exit 0
			;;
		-k|--keep)
			keep() { echo "Kept $tempdir"; }
			shift
			;;
		-psd|--print-source-directories)
			psd=3
			shift
			;;
		-d)
			(( $# < 2 )) &&
				echo "'-d': No directory specified" &&
					usage && exit 1
			directory=$(readlink -f "$2")
			shift
			shift
			;;
		--directory=*)
			(( $# < 2 )) &&
				echo "'--directory=': No directory specified" &&
					usage && exit 1
			directory=$(readlink -f "${1#*=}")
			shift
			;;
		*)
			. ~/config/settings/haikuports.conf
			directory=$(
				find "$TREE_PATH" -iname "$1-*.*.recipe" |
					awk 'FNR == 1 { gsub("/[^/]*$", "")
							print }'
			)
			portName="$1"
			#directory=$(haikuporter -o "$1")
			shift
			;;
	esac
	args=$#
done

cd "$directory" || die "Invalid recipe location."
tempdir=$(mktemp -d "$port".XXXXXX --tmpdir=/tmp)
trap 'cd $OLDPWD; keep; trap - EXIT RETURN' EXIT RETURN
set -- "$portName"*-*.recipe
eval "recipe=\${$#}"

port=${recipe%.*}
portName=${port%-*}
portVersion=${port##*-}

defineDebugInfoPackage() { :; }

eval "$(cat "$recipe")" || die "Error in sourcing the recipe file."

case "" in
	$directory)
		die "Could not find the recipe's location."
		;;
	$SOURCE_URI)
		die "The recipe does not set SOURCE_URI."
		;;
	$SOURCE_FILENAME)
		SOURCE_FILENAME=$(basename "$SOURCE_URI")
		;;
	$SOURCE_DIR)
		SOURCE_DIR="$port"
		;;
esac

mkdir -p download
for ((i=0; i<3; i++)); do
	echo "$CHECKSUM_SHA256  download/$SOURCE_FILENAME" | sha256sum -c \
			&& break ||
		((i<2)) && wget -O download/"$SOURCE_FILENAME" "$SOURCE_URI" \
			"$( ((i<1)) && echo '-c' )"
done || die "Checksum verification failed."

for ((i=0; i<3; i++)); do
	tar --transform "s/$SOURCE_DIR/${tempdir##*/}/" -C /tmp \
		-xf download/"$SOURCE_FILENAME" \
		"$SOURCE_DIR"/"$( ((i<2)) && echo "Cargo.lock" )" && ((i<2)) && break
	((i>1)) && {
		[ -n "$PATCHES" ] && patch -d "$tempdir" -i patches/"$PATCHES"
		(cd "$tempdir" && cargo update)
	}
done

info=$(
	sed -e '0,/\[metadata\]/d
		s/checksum //
		s/(.*)//
		s/ /-/
		s/ = //
		s/"//g' "$tempdir"/Cargo.lock
)
mapfile -t crates < <(awk '{ print $1".crate" }' <<< "$info")
mapfile -t checksums < <(awk '{ print $2 }' <<< "$info")
mapfile -t uris < <(
	for crate in "${crates[@]}"; do
		echo "https://static.crates.io/crates/${crate%-*}/$crate"
	done
)

unset source_uris checksums_sha256 source_dirs merged
for i in $(seq 0 $(($(wc -l <<< "$info") - 1))); do
	j=$((i + 2))
	source_uris+=( "SOURCE_URI_$j=\"${uris[i]}\"" )
	checksums_sha256+=( "CHECKSUM_SHA256_$j=\"${checksums[i]}\"" )
	[ "$psd" = 3 ] && source_dirs+=("$(
		source_filename=$(basename --suffix=.crate "${source_uris[i]}")
		echo SOURCE_DIR_$j=\""$source_filename"\"
	)")
	merged+=( ${source_uris[i]} ${checksums_sha256[i]} ${source_dirs[i]} )
done
printf '%s\n' "${merged[@]}" | sed '0~'"$psd"' a\\'
