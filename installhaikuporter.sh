#!/bin/sh

_progress () {
	notify --type progress \
		--app haikuporter \
		--icon `finddir B_SYSTEM_APPS_DIRECTORY`/PackageInstaller \
		--messageID $0_$$ \
		--title "Install haikuporter..." \
		--progress "$1" "$2" >/dev/null
}

_progress 0.0 "haikuporter"
	cd `finddir B_COMMON_DEVELOP_DIRECTORY`
	svn co http://ports.haiku-files.org/svn/haikuporter/trunk haikuporter

_progress 0.2 "haikuporter setup"
	cd `finddir B_COMMON_DEVELOP_DIRECTORY`/haikuporter
	cp haikuporter $(finddir B_COMMON_BIN_DIRECTORY)/haikuporter > /dev/null
	echo "# HaikuPorts configuration" > haikuports.conf
	echo "" >> haikuports.conf
	echo "PACKAGES_PATH="\"$(finddir B_COMMON_DEVELOP_DIRECTORY)/haikuports\" >> haikuports.conf
  	cp haikuports.conf $(finddir B_COMMON_ETC_DIRECTORY)/haikuports.conf > /dev/null

_progress 0.6 "check for python"
	if [ ! -e `finddir B_COMMON_BIN_DIRECTORY`/python ]; then
		_progress 0.7 "trying to install python"
		installoptionalpackage python
	fi
_progress 0.8 "update haikuports"
	haikuporter -g
_progress 0.9 "haikuports"
	haikuporter -l
_progress 1.0 ""
