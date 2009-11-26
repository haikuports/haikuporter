#!/bin/sh
cd $(finddir B_COMMON_DEVELOP_DIRECTORY)
if [ ! -f $(finddir B_COMMON_DEVELOP_DIRECTORY)/haikuporter/haikuporter ] ; then
svn co http://ports.haiku-files.org/svn/haikuports/trunk haikuports
svn co http://ports.haiku-files.org/svn/haikuporter/trunk haikuporter
fi

alert --idea "Install haikuporter?" Yes No > /dev/null
button=$?
if [ $button -eq 0 ] ; then
		cd /boot/develop/haikuporter
  		cp haikuporter $(finddir B_COMMON_BIN_DIRECTORY)/haikuporter > /dev/null
		echo "# HaikuPorts configuration" > haikuports.conf
		echo "" >> haikuports.conf
        echo "PACKAGES_PATH="\"$(finddir B_COMMON_DEVELOP_DIRECTORY)/haikuports\" >> haikuports.conf
        cp haikuports.conf $(finddir B_COMMON_ETC_DIRECTORY)/haikuports.conf > /dev/null
  		alert "haikuporter is ready." > /dev/null
else
		alert --stop "haikuporter is not installed." > /dev/null
fi
