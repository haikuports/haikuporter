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


# -- sysExit ------------------------------------------------------------------
def sysExit(message):
	"""wrap invocation of sys.exit()"""
	
	message = '\n'.join(['*** ' + line for line in message.split('\n') ])
	sys.exit(message)


# -- warn ---------------------------------------------------------------------
def warn(message):
	"""print a warning"""
	
	message = '\n'.join(['* ' + line for line in message.split('\n') ])
	print(message)


# -- findDirectory ------------------------------------------------------------
def findDirectory(aDir):
	"""wraps invocation of 'finddir'"""
	
	return check_output(['/bin/finddir', aDir]).rstrip()  # drop newline

# -- quote --------------------------------------------------------------------
def escapeForPackageInfo(string):
	"""escapes string to be used within "" quotes in a .PackageInfo file"""
	
	return string.replace('\\', '\\\\').replace('"', '\\"')


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
