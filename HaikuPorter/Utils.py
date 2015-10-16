# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import glob
import os
import re
import shutil
from subprocess import PIPE, Popen, CalledProcessError
import sys
import tarfile
import zipfile

if sys.stdout.isatty():
	colorWarning = '\033[1;36m'
	colorError = '\033[1;35m'
	colorReset = '\033[1;m'
else:
	colorWarning= ''
	colorError = ''
	colorReset = ''

# -- MyTarInfo -------------------------------------------------------------

class MyTarInfo(tarfile.TarInfo):
	"""Override tarfile.TarInfo in order to automatically treat hardlinks
	   contained in tar archives as symbolic links during extraction.
	"""
	@classmethod
	def frombuf(cls, buf):
		tarinfo = tarfile.TarInfo.frombuf(buf)
		if tarinfo.type == tarfile.LNKTYPE:
			tarinfo.type = tarfile.SYMTYPE
		return tarinfo

	@classmethod
	def fromtarfile(cls, theTarfile):
		tarinfo = tarfile.TarInfo.fromtarfile(theTarfile)
		if tarinfo.type == tarfile.LNKTYPE:
			tarinfo.type = tarfile.SYMTYPE
		return tarinfo

# path to haikuports-tree --------------------------------------------------
haikuportsRepoUrl = 'git@github.com:haikuports/haikuports.git'

# path to haikuporter-tree
haikuporterRepoUrl = 'git@github.com:haikuports/haikuporter.git'

def sysExit(message):
	"""wrap invocation of sys.exit()"""

	message = '\n'.join([colorError + 'Error: ' + line + colorReset
		for line in message.split('\n') ])
	sys.exit(message)


def warn(message):
	"""print a warning"""

	message = '\n'.join([colorWarning + 'Warning: ' + line +colorReset
		for line in message.split('\n') ])
	print(message)


def printError(*args):
	"""print a to stderr"""

	sys.stderr.write(' '.join(map(str, args)) + '\n')


def escapeForPackageInfo(string):
	"""escapes string to be used within "" quotes in a .PackageInfo file"""

	return string.replace('\\', '\\\\').replace('"', '\\"')

def unpackArchive(archiveFile, targetBaseDir, subdir):
	"""Unpack archive into a directory"""

	## REFACTOR into separate functions and dispatch

	if subdir and not subdir.endswith('/'):
		subdir += '/'
	# unpack source archive
	if tarfile.is_tarfile(archiveFile):
		tarFile = tarfile.open(archiveFile, 'r', tarinfo=MyTarInfo)
		members = None
		if subdir:
			members = [
				member for member in tarFile.getmembers()
				if os.path.normpath(member.name)
					.startswith(subdir) and not os.path.normpath(member.name)
					.endswith("/.git")
			]
			if not members:
				sysExit('sub-directory %s not found in archive' % subdir)
			if hasattr(os, "geteuid") and os.geteuid() == 0:
				for member in members:
					member.gname = ""
					member.uname = ""
					member.gid = 0
					member.uid = 0
		tarFile.extractall(targetBaseDir, members)
		tarFile.close()
	elif zipfile.is_zipfile(archiveFile):
		zipFile = zipfile.ZipFile(archiveFile, 'r')
		names = None
		if subdir:
			names = [
				name for name in zipFile.namelist()
				if os.path.normpath(name).startswith(subdir)
			]
			if not names:
				sysExit('sub-directory %s not found in archive' % subdir)
		zipFile.extractall(targetBaseDir, names)
		zipFile.close()
	elif archiveFile.split('/')[-1].split('.')[-1] == 'xz':
		ensureCommandIsAvailable('xz')
		Popen(['xz', '-f', '-d', '-k', archiveFile]).wait()
		tar = archiveFile[:-3]
		if tarfile.is_tarfile(tar):
			tarFile = tarfile.open(tar, 'r', tarinfo=MyTarInfo)
			members = None
			if subdir:
				if not subdir.endswith('/'):
					subdir += '/'
				members = [
					member for member in tarFile.getmembers()
					if os.path.normpath(member.name)
						.startswith(subdir)
				]
				if not members:
					sysExit('sub-directory %s not found in archive' % subdir)
			tarFile.extractall(targetBaseDir)
			tarFile.close()
			os.remove(tar)
	elif archiveFile.split('/')[-1].split('.')[-1] == 'lz':
		ensureCommandIsAvailable('lzip')
		Popen(['lzip', '-f', '-d', '-k', archiveFile]).wait()
		tar = archiveFile[:-3]
		if tarfile.is_tarfile(tar):
			tarFile = tarfile.open(tar, 'r', tarinfo=MyTarInfo)
			members = None
			if subdir:
				if not subdir.endswith('/'):
					subdir += '/'
				members = [
					member for member in tarFile.getmembers()
					if os.path.normpath(member.name)
						.startswith(subdir)
				]
				if not members:
					sysExit('sub-directory %s not found in archive' % subdir)
			tarFile.extractall(targetBaseDir)
			tarFile.close()
			os.remove(tar)
	else:
		sysExit('Unrecognized archive type in file '
				+ archiveFile)

def symlinkDirectoryContents(sourceDir, targetDir, emptyTargetDirFirst = True):
	"""Populates targetDir with symlinks to all files from sourceDir"""

	files = [sourceDir + '/' + fileName for fileName in os.listdir(sourceDir) ]
	symlinkFiles(files, targetDir)

def symlinkGlob(globSpec, targetDir, emptyTargetDirFirst = True):
	"""Populates targetDir with symlinks to all files matching given globSpec"""

	files = glob.glob(globSpec)
	symlinkFiles(files, targetDir)

def symlinkFiles(sourceFiles, targetDir, emptyTargetDirFirst = True):
	"""Populates targetDir with symlinks to all the given files"""

	if os.path.exists(targetDir) and emptyTargetDirFirst:
		shutil.rmtree(targetDir)
	if not os.path.exists(targetDir):
		os.makedirs(targetDir)
	for sourceFile in sourceFiles:
		os.symlink(sourceFile, targetDir + '/' + os.path.basename(sourceFile))

def touchFile(theFile):  # @DontTrace
	"""Touches given file, making sure that its modification date is bumped"""

	if os.path.exists(theFile):
		os.utime(theFile, None)
	else:
		open(theFile, 'w').close()

def storeStringInFile(string, theFile):
	"""Stores the given string in the file with the given name"""

	with open(theFile, 'w') as fo:
		fo.write(string)

def readStringFromFile(theFile):
	"""Returns the contents of the file with the given name as a string"""

	with open(theFile, 'r') as fo:
		return fo.read()

availableCommands = {}
def isCommandAvailable(command):
	"""returns whether the given command is available"""

	if command in availableCommands:
		return availableCommands[command]

	for path in os.environ['PATH'].split(':'):
		if os.path.exists(path + '/' + command):
			availableCommands[command] = True
			return True

	availableCommands[command] = False
	return False

def ensureCommandIsAvailable(command):
	"""checks if the given command is available and bails if not"""

	if not isCommandAvailable(command):
		sysExit("'" + command + "' is not available, please install it")

def naturalCompare(left, right):
	"""performs a natural compare between the two given strings - returns:
		-1 if left is lower than right
		 1 if left is higher than right
		 0 if both are equal"""

	convert = lambda text: int(text) if text.isdigit() else text.lower()
	alphanum_key = lambda key: [ convert(c) for c in re.split('([0-9]+)', key) ]
	return cmp(alphanum_key(left), alphanum_key(right))

def bareVersionCompare(left, right):
	"""Compares two given bare versions - returns:
		-1 if left is lower than right
		 1 if left is higher than right
		 0 if both versions are equal"""

	leftElements = left.split('.')
	rightElements = right.split('.')

	index = 0
	leftElementCount = len(leftElements)
	rightElementCount = len(rightElements)
	while True:
		if index + 1 > leftElementCount:
			if index + 1 > rightElementCount:
				return 0
			else:
				return -1
		elif index + 1 > rightElementCount:
			return 1

		result = naturalCompare(leftElements[index], rightElements[index])
		if result != 0:
			return result

		index += 1

def versionCompare(left, right):
	"""Compares two given versions that may include a pre-release - returns
		-1 if left is lower than right
		 1 if left is higher than right
		 0 if both versions are equal"""

	leftElements = left.split('~', 1)
	rightElements = right.split('~', 1)

	result = bareVersionCompare(leftElements[0], rightElements[0])
	if result != 0:
		return result

	if len(leftElements) < 2:
		if len(rightElements) < 2:
			return 0
		else:
			return -1
	elif len(rightElements) < 2:
		return 1

	# compare pre-release strings
	return naturalCompare(leftElements[1], rightElements[1])

def filteredEnvironment():
	"""returns a filtered version of os.environ, such that none of the
	   variables that we export for one port leak into the shell environment
	   of another"""

	env = {}

	for key in ['LANG', 'LIBRARY_PATH', 'PATH']:
		if key in os.environ:
			env[key] = os.environ[key]

	return env
