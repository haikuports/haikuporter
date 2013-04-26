# -*- coding: utf-8 -*-
# copyright 2013 Oliver Tappe

# -- Modules ------------------------------------------------------------------

import glob
import os
import shutil
from subprocess import PIPE, Popen, CalledProcessError
import sys
import tarfile
import zipfile


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


# -- frequently used directories ----------------------------------------------
systemDir = {
	'B_COMMON_DIRECTORY': None,
	'B_COMMON_PACKAGES_DIRECTORY': None,
	'B_PACKAGE_LINKS_DIRECTORY': None,
	'B_SYSTEM_DIRECTORY': None,
	'B_SYSTEM_PACKAGES_DIRECTORY': None,
}
for key in systemDir.keys():
	systemDir[key] = findDirectory(key)

# -- escapeForPackageInfo -----------------------------------------------------
def escapeForPackageInfo(string):
	"""escapes string to be used within "" quotes in a .PackageInfo file"""
	
	return string.replace('\\', '\\\\').replace('"', '\\"')

# -- unpackArchive ------------------------------------------------------------
def unpackArchive(archiveFile, targetBaseDir):
	"""Unpack archive into a directory"""

	# unpack source archive
	if tarfile.is_tarfile(archiveFile):
		tarFile = tarfile.open(archiveFile, 'r')
		tarFile.extractall(targetBaseDir)
		tarFile.close()
	elif zipfile.is_zipfile(archiveFile):
		zipFile = zipfile.ZipFile(archiveFile, 'r')
		zipFile.extractall(targetBaseDir)
		zipFile.close()
	elif archiveFile.split('/')[-1].split('.')[-1] == 'xz':
		ensureCommandIsAvailable('xz')
		Popen(['xz', '-d', '-k', archiveFile]).wait()
		tar = archiveFile[:-3]
		if tarfile.is_tarfile(tar):
			tarFile = tarfile.open(tar, 'r')
			tarFile.extractall(targetBaseDir)
			tarFile.close()
	else:
		sysExit('Unrecognized archive type in file ' 
				+ archiveFile)

# -- symlinkDirectoryContents -------------------------------------------------
def symlinkDirectoryContents(sourceDir, targetDir, emptyTargetDirFirst = True):
	"""Populates targetDir with symlinks to all files from sourceDir"""
	
	files = [sourceDir + '/' + fileName for fileName in os.listdir(sourceDir) ]
	symlinkFiles(files, targetDir)
	
# -- symlinkGlob --------------------------------------------------------------
def symlinkGlob(globSpec, targetDir, emptyTargetDirFirst = True):
	"""Populates targetDir with symlinks to all files matching given globSpec"""
	
	files = glob.glob(globSpec)
	symlinkFiles(files, targetDir)
	
# -- symlinkFiles -------------------------------------------------------------
def symlinkFiles(sourceFiles, targetDir, emptyTargetDirFirst = True):
	"""Populates targetDir with symlinks to all the given files"""
	
	if os.path.exists(targetDir) and emptyTargetDirFirst:
		shutil.rmtree(targetDir)
	if not os.path.exists(targetDir):
		os.makedirs(targetDir)
	for sourceFile in sourceFiles:
		os.symlink(sourceFile, targetDir + '/' + os.path.basename(sourceFile))


# -- ensureCommandIsAvailable -------------------------------------------------
availableCommands = {}

def ensureCommandIsAvailable(command):
	"""checks if the given command is available and bails if not"""

	if command not in availableCommands:
		for path in os.environ['PATH'].split(':'):
			if os.path.exists(path + '/' + command):
				availableCommands[command] = True
				break
		else:
			sysExit("'" + command + "' is not available, please install it")
