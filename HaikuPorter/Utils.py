# -*- coding: utf-8 -*-
# copyright 2013 Oliver Tappe

# -- Modules ------------------------------------------------------------------

from subprocess import PIPE, Popen, CalledProcessError
import sys


# -- capture output of shell command -----------------------------------------
def check_output(*popenargs, **kwargs):
	"""local clone of subprocess.check_output() provided by python-2.7
	   TODO: drop this once we have upgraded python to 2.7"""
	process = Popen(stdout=PIPE, *popenargs, **kwargs)
	output, unused_err = process.communicate()
	retcode = process.poll()
	if retcode:
		cmd = kwargs.get("args")
		if cmd is None:
			cmd = popenargs[0]
		raise CalledProcessError(retcode, cmd)
	return output


# -- wraps invocation of sys.exit() ------------------------------------------
def sysExit(message):
	message = '\n'.join(['*** ' + line for line in message.split('\n') ])
	sys.exit(message)


# -- prints a warning --------------------------------------------------------
def warn(message):
	message = '\n'.join(['* ' + line for line in message.split('\n') ])
	print(message)


# -- wraps invocation of 'finddir' -------------------------------------------
def findDirectory(aDir):
	return check_output(['/bin/finddir', aDir]).rstrip()  # drop newline


# ----------------------------------------------------------------------------

# Frequently used directories
systemDir = {
	'B_COMMON_DIRECTORY': None,
	'B_COMMON_PACKAGES_DIRECTORY': None,
	'B_PACKAGE_LINKS_DIRECTORY': None,
	'B_SYSTEM_DIRECTORY': None,
	'B_SYSTEM_PACKAGES_DIRECTORY': None,
}
for key in systemDir.keys():
	systemDir[key] = findDirectory(key)
