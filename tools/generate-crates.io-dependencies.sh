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

psd=2
args=1
while (( args > 0 )); do
	case "$1" in
		""|-h|--help )
			usage
			exit 0
			;;
		-k|--keep)
			keep=1
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
set -- "$portName"*-*.recipe
eval "recipe=\${$#}"

port=${recipe%.*}
portName=${port%-*}
portVersion=${port##*-}

defineDebugInfoPackage() { :; }

. "$recipe" || die "Error in sourcing the recipe file."

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

tempdir=$(mktemp -d "$port".XXXXXX --tmpdir=/tmp)
if [ -z "$keep" ]; then
	trap 'rm -rf $tempdir' EXIT RETURN
else
	trap 'echo Kept $tempdir' EXIT RETURN
fi

for ((i=0; i<3; i++)); do
	tar --transform "s/$SOURCE_DIR/${tempdir##*/}/" -C /tmp \
		-xf download/"$SOURCE_FILENAME" \
		"$SOURCE_DIR"/$( ((i<2)) && echo "Cargo.lock" ) &&
		((i<2)) && break
	((i>1)) && {
		[ -n "$PATCHES" ] && patch -d "$tempdir" -i patches/"$PATCHES"
		(cd "$tempdir" && cargo update)
	}
done
cd "$OLDPWD"

info=$(
	sed -e '0,/\[metadata\]/d
		s/checksum //
		s/(.*)//
		s/ /-/
		s/ = //
		s/"//g' "$tempdir"/Cargo.lock
)
crates=$(awk '{ print $1".crate" }' <<< "$info")
checksums=$(awk '{ print $2 }' <<< "$info")
numbers=$(seq 2 $(($(wc -l <<< "$info") + 1)))

uris=$(
	for crate in $crates; do
		echo "https://static.crates.io/crates/${crate%-*}/$crate"
	done
)
source_uris=$(
	for i in $numbers; do
		echo SOURCE_URI_$i=\""$(sed "$((i-1))q;d" <<< "$uris")"\"
	done
)
checksums_sha256=$(
	for i in $numbers; do
		j=$((i - 1))
		echo CHECKSUM_SHA256_$i=\""$(sed "${j}q;d" <<< "$checksums")"\"
	done
)
source_dirs=$(
	eval "$source_uris"
	for i in $numbers; do
		eval source_uri=\$SOURCE_URI_$i
		source_filename=$(basename --suffix=.crate "$source_uri")
		echo SOURCE_DIR_$i=\""$source_filename"\"
	done
)

merged=$(paste -d \\n <(echo "$source_uris") <(echo "$checksums_sha256"))
if [ "$psd" = 3 ]; then
	for i in $numbers; do
		merged=$(sed "/CHECKSUM_SHA256_$i=\".*\"/a \
			$(sed "$((i-1))q;d" <<< "$source_dirs")" <<< "$merged")
	done
fi
echo "$merged" | sed '0~'"$psd"' a\\'
