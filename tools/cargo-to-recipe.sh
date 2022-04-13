#!/usr/bin/env bash

die() {
	printf %s "${*+$'\e[31merror: \e[0m'$*$'\n'}"
	(( usage )) && usage
	exit 1
} >&2

usage() {
	cat <<-EOF
	Usage: $0 [options] [uri://to/source-tarball] category/port

	Creates a recipe template for a crates.io package, filled with
	information at hand. Requires awk, coreutils, sed, tar (with the
	appropriate decompression utility), and wget.

	Options:
	  -h, --help	show this help message and exit
	  -k, --keep	keep the generated temporary directory
	  -nc, --no-clobber
	 		do not overwrite existing files
	  -psd, --print-source-directories
	 		also print SOURCE_DIRs
	  -b, --bump
	 		bump the crates.io dependencies of the port's highest
	 		versioned recipe instead (overrides --no-clobber)
	  -c CMD, --cmd=CMD
	 		specify the command runtime
	EOF
}

temp() { rm -rf "$tempdir"; }

. "$(finddir B_USER_SETTINGS_DIRECTORY)"/haikuports.conf
(( $# )) || usage=1 die
while (( $# )); do
	case $1 in
		-h|--help)
			usage
			exit 0
			;;
		-k|--keep)
			temp() { printf '%s\n' "Kept $tempdir"; }
			;;
		-nc|--no-clobber)
			nc=1
			shopt -s expand_aliases
			alias mv='mv -n'
			alias cp='cp -n'
			;;
		-psd|--print-source-directories)
			psd=3
			;;
		-b|--bump)
			bump=1
			;;
		-c)
			shift
			;&
		--cmd=*)
			cmd=${1#*=}
			;;
		*://*)
			SOURCE_URI=$1
			;;
		*-*/*)
			directory=$TREE_PATH/$1
			: "${1//-/_}"
			portName=${_#*/}
			;;
		-?*)
			usage=1 die "Invalid option."
			;;
		*)
			usage=1 die "Invalid argument."
			;;
	esac
	shift
done

mkdir -p "$directory"/download
cd "$directory" || die "Invalid port directory."

if (( bump )); then
	eval "recipe=$(
		ls -v --quoting-style=shell-escape \
			"$portName"-[0-9]*.[0-9]*.[0-9]*.recipe | tail -n 1
	)"

	portVersionedName=${recipe%.recipe}
	portVersion=${portVersionedName#$portName-}

	defineDebugInfoPackage() { :; }
	getPackagePrefix() { :; }

	. "$recipe" || die "Sourcing the recipe file failed."
fi

: "${cmd:=$portName}" "${psd:=2}" "${SOURCE_URI%/}"
source_file=${_##*/}
: "${SOURCE_FILENAME:=$source_file}"

case "" in
	$directory)
		usage=1 die "No category and/or port specified."
		;;&
	$SOURCE_URI)
		usage=1 die "SOURCE_URI is empty or unset."
		;;&
	$CHECKSUM_SHA256)
		if [[ nc -eq 0 || ! -e download/$SOURCE_FILENAME ]]; then
			wget -O download/"$SOURCE_FILENAME" "$SOURCE_URI" ||
				die "Failed to download the source file."
		fi
		CHECKSUM_SHA256=1
		;;
esac

if [[ $CHECKSUM_SHA256 != 1 ]]; then
	for (( i = 0; i < 3; ++i )); do
		printf '%s\n' "$CHECKSUM_SHA256  download/$SOURCE_FILENAME" |
			sha256sum -c && break
		(( i < 2 )) && wget -O download/"$SOURCE_FILENAME" \
			"$( (( i < 1 )) && printf -- "-c")" "$SOURCE_URI"
	done || die "Checksum verification failed."
else
	: "$(sha256sum download/"$SOURCE_FILENAME")"
	CHECKSUM_SHA256=${_::64}
fi

: "$(tar --exclude=*/* -tf download/"$SOURCE_FILENAME")"
SOURCE_DIR=${_%/}
if test "$SOURCE_FILENAME" != "$SOURCE_DIR.tar.${source_file##*.}"; then
	mv download/{"$SOURCE_FILENAME","$_"}
	SOURCE_FILENAME=${_##*/}
fi

tempdir=$(mktemp -d -t "$SOURCE_DIR".XXXXXX)
trap temp 0
tar --transform "s|$SOURCE_DIR|${tempdir##*/}|" -C /tmp \
	-xf download/"$SOURCE_FILENAME" --wildcards "$SOURCE_DIR/Cargo.*" ||
	die "Failed to extract the necessary files."

info=$(
	if grep -q '\[metadata\]' "$tempdir"/Cargo.lock; then
		sed -e '0,/\[metadata\]/d
			s/checksum //
			s/(.*)//
			s/ /-/
			s/ = //
			s/"//g' "$tempdir"/Cargo.lock
	else
		awk -F \" '
		/name|version|checksum/ {
			if ($1 ~ "name")
				i += 1
			data[i] = data[i] "," $2
		}

		END {
			for (j in data) {
				split(data[j], f, ",")
				if (length(f[4]) == 64)
					print f[2] " " f[3] " " f[4]
			}
		}' "$tempdir"/Cargo.lock | sort | sed 's/ /-/'
	fi
)

mapfile -t crates < <(awk '{ print $1".crate" }' <<< "$info")
mapfile -t checksums < <(awk '{ print $2 }' <<< "$info")
echo "$info"
for crate in "${crates[@]}"; do
	uris+=("https://static.crates.io/crates/${crate%%-[0-9]*.[0-9]*.[0-9]*}/$crate")
	(( psd == 3 )) && dirs+=("${crate%.crate}")
done

for (( i = 0; j = i+2, i < ${#crates[@]}; i++ )); do
	source_uris+=("SOURCE_URI_$j=\"${uris[i]}\"")
	checksums_sha256+=("CHECKSUM_SHA256_$j=\"${checksums[i]}\"")
	merged+=("${source_uris[i]}" "${checksums_sha256[i]}")
	(( psd == 3 )) && {
		source_dirs+=("SOURCE_DIR_$j=\"${dirs[i]}\"")
		merged+=("${source_dirs[i]}")
	}
done

if (( bump )); then
	sed -i \
		-e '/SOURCE_URI_2/,/ARCHITECTURES/ { /^A/!d }' \
		-e "/^ARCHITECTURES/i $(printf '%s\n' "${merged[@]}" |
			sed '0~'"$psd"' a\\' | head -n -1 |
			sed -z 's/\n/\\n/g')" \
		-e "s/{2\.\.[0-9]\+}/{2..$(( "${#crates[@]}" + 1 ))}/" \
		"$recipe"
	exit
fi

eval "$(
	sed -n '/\[package\]/,/^$/ {
		/"""\|\[/d
		s/-\(.*=\)/_\1/
		s/ = /=/p
	}' "$tempdir"/Cargo.toml
)"
cat <<EOF >"$tempdir/$portName-$version.recipe"
SUMMARY="${description%.}"
DESCRIPTION="$(
	extended=$(
		grep -q extended-description "$tempdir"/Cargo.toml &&
			printf "extended-"
	)

	sed -n "/${extended}description"' = """/,/"""/ {
		s/.*description = //
		s/"""//g
		/^$/d
		p
	}' "$tempdir"/Cargo.toml
)"
HOMEPAGE="$homepage"
COPYRIGHT=""
LICENSE="$(
	IFS=$'\n' read -d "" -ra licenses <<< "$(
		sed -e 's,/\| AND \| OR ,\n,g
			s,-\([0-9]\)\.0, v\1,g' <<< "$license" | sort
	)"
	printf %s "${licenses[0]}"
	(( ${#licenses[@]} > 1 )) && printf '\n\t%s' "${licenses[@]:1}"
)"
REVISION="1"
SOURCE_URI="$(
	: "${SOURCE_URI//$version/\$portVersion}"
	printf '%s\n' "${_/$homepage/\$HOMEPAGE}"
)"
CHECKSUM_SHA256="$CHECKSUM_SHA256"
$(
	if [[ $source_file != "$SOURCE_FILENAME" ]]; then
		: "${SOURCE_FILENAME/$version/\$portVersion}"
		printf '%s\n' "SOURCE_FILENAME=\"$_\""
	fi
	printf '\n'
	printf '%s\n' "${merged[@]}" | sed '0~'"$psd"' a\\'
)

ARCHITECTURES="!x86_gcc2 ?x86 ?x86_64"
commandBinDir=\$binDir
if [ "\$targetArchitecture" = x86_gcc2 ]; then
SECONDARY_ARCHITECTURES="?x86"
commandBinDir=\$prefix/bin
fi

PROVIDES="
	$portName\$secondaryArchSuffix = \$portVersion
	cmd:$cmd
	"
REQUIRES="
	haiku\$secondaryArchSuffix
	"

BUILD_REQUIRES="
	haiku\${secondaryArchSuffix}_devel
	"
BUILD_PREREQUIRES="
	cmd:cargo\$secondaryArchSuffix
	cmd:gcc\$secondaryArchSuffix
	"

defineDebugInfoPackage $portName\$secondaryArchSuffix \\
	"\$commandBinDir"/$cmd

BUILD()
{
	export CARGO_HOME=\$sourceDir/../cargo
	vendor=\$CARGO_HOME/haiku
	mkdir -p "\$vendor"
	for i in \$(seq 2 $(( ${#crates[@]} + 1 ))); do
		eval "srcDir=\\\$sourceDir\$i"
		eval "sha256sum=\\\$CHECKSUM_SHA256_\$i"
		set -- "\$srcDir"$(
			(( psd == 2 )) && printf "/*"
		)
		ln -sf "\$1" "\$vendor"
		cat <<-EOF >"\$vendor/\${1##*/}/.cargo-checksum.json"
		{
		  "package": "\$sha256sum",
		  "files": {}
		}
		EOF
	done

	cat <<-EOF >"\$CARGO_HOME"/config
	[source.haiku]
	directory = "\$vendor"

	[source.crates-io]
	replace-with = "haiku"
	EOF

	cargo build --release --frozen
}

INSTALL()
{
	install -m 755 -d "\$commandBinDir" "\$docDir"
	install -m 755 target/release/$cmd "\$commandBinDir"
	install -m 644 README.md "\$docDir"
}

TEST()
{
	export CARGO_HOME=\$sourceDir/../cargo
	cargo test --release --frozen
}
EOF
cp "$tempdir/$portName-$version.recipe" .

if [[ -v license_file ]]; then
	cat <<-EOF
	-----------------------------------------------------------------------
	This port uses a custom license file.
	It will be installed to the port's license directory; please rename it
	as appropriate and add it to the recipe.
	EOF
	tar --transform "s|$SOURCE_DIR|${tempdir##*/}|" -C /tmp \
		-xf download/"$SOURCE_FILENAME" "${license_file/#./$SOURCE_DIR}"
	mkdir -p licenses
	cp "$tempdir"/"$license_file" licenses
fi
