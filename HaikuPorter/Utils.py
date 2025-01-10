# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import codecs
import copy
import glob
import logging
import os
import re
import shutil
import sys
import tarfile
import time
import zipfile
from subprocess import PIPE, Popen

if sys.stdout.isatty():
	colorStatus = '\033[1;34m'
	colorWarning = '\033[1;36m'
	colorError = '\033[1;35m'
	colorReset = '\033[1;m'
else:
	colorStatus = ''
	colorWarning = ''
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
			tarinfo.linkname = os.path.join(os.path.relpath(os.path.dirname(
				tarinfo.linkname), os.path.dirname(tarinfo.name)),
				os.path.basename(tarinfo.linkname))
		return tarinfo

	@classmethod
	def fromtarfile(cls, theTarfile):
		tarinfo = tarfile.TarInfo.fromtarfile(theTarfile)
		if tarinfo.type == tarfile.LNKTYPE:
			tarinfo.type = tarfile.SYMTYPE
			tarinfo.linkname = os.path.join(os.path.relpath(os.path.dirname(
				tarinfo.linkname), os.path.dirname(tarinfo.name)),
				os.path.basename(tarinfo.linkname))
		return tarinfo

# path to haikuports-tree --------------------------------------------------
haikuportsRepoUrl = 'https://github.com/haikuports/haikuports.git'

# path to haikuporter-tree
haikuporterRepoUrl = 'https://github.com/haikuports/haikuporter.git'

def sysExit(message):
	"""wrap invocation of sys.exit()"""

	message = '\n'.join([colorError + 'Error: ' + line + colorReset
		for line in message.split('\n')])
	sys.exit(message)

def warn(message):
	"""print a warning"""
	message = '\n'.join([colorWarning + 'Warning: ' + line + colorReset
		for line in message.split('\n')])
	logging.getLogger("buildLogger").warn(message)

def important(message):
	"""print an important"""
	message = '\n'.join([colorStatus + '=== ' + line + colorReset
		for line in message.split('\n')])
	logging.getLogger("buildLogger").warn(message)

def info(message):
	"""print an info"""
	if message is not None and message != '':
		logging.getLogger("buildLogger").info(message if message[-1] != '\n'
			else message[:-1])

def printError(*args):
	"""print a to stderr"""

	sys.stderr.write(' '.join([str(arg) for arg in args]) + '\n')


def escapeForPackageInfo(string):
	"""escapes string to be used within "" quotes in a .PackageInfo file"""

	return string.replace('\\', '\\\\').replace('"', '\\"')

def unpackArchive(archiveFile, targetBaseDir, subdir):
	"""Unpack archive into a directory"""

	## REFACTOR into separate functions and dispatch

	process = None
	if not tarfile.is_tarfile(archiveFile):
		ext = archiveFile.split('/')[-1].split('.')[-1]
		if ext == 'lz':
			ensureCommandIsAvailable('lzip')
			process = Popen(['lzip', '-c', '-d', archiveFile],
				bufsize=10240, stdin=PIPE, stdout=PIPE, stderr=PIPE)
		elif ext == '7z':
			ensureCommandIsAvailable('7za')
			process = Popen(['7za', 'x', '-so', archiveFile],
				bufsize=10240, stdin=PIPE, stdout=PIPE, stderr=PIPE)
		elif ext == 'zst':
			ensureCommandIsAvailable('zstd')
			process = Popen(['zstd', '-c', '-d', archiveFile],
				bufsize=10240, stdin=PIPE, stdout=PIPE, stderr=PIPE)

	if subdir and not subdir.endswith('/'):
		subdir += '/'
	# unpack source archive or the decompressed stream
	if process or tarfile.is_tarfile(archiveFile):
		tarFile = None
		if process:
			tarFile = tarfile.open(fileobj=process.stdout, mode='r|',
				tarinfo=MyTarInfo)
		else:
			tarFile = tarfile.open(archiveFile, 'r', tarinfo=MyTarInfo)

		if subdir is None:
			tarFile.extractall(path=targetBaseDir)
		else:
			def filterByDir(members):
				for member in members:
					member = copy.copy(member)
					if (os.path.normpath(member.name).startswith(subdir)
							and not os.path.normpath(member.name).endswith("/.git")):
						if hasattr(os, "geteuid") and os.geteuid() == 0:
							member.gname = ""
							member.uname = ""
							member.gid = 0
							member.uid = 0
						yield member
			tarFile.extractall(members=filterByDir(tarFile), path=targetBaseDir)
			
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
	else:
		sysExit('Unrecognized archive type in file '
				+ archiveFile)

def symlinkDirectoryContents(sourceDir, targetDir, emptyTargetDirFirst=True):
	"""Populates targetDir with symlinks to all files from sourceDir"""

	files = [sourceDir + '/' + fileName for fileName in os.listdir(sourceDir)]
	symlinkFiles(files, targetDir)

def symlinkGlob(globSpec, targetDir, emptyTargetDirFirst=True):
	"""Populates targetDir with symlinks to all files matching given globSpec"""

	files = glob.glob(globSpec)
	symlinkFiles(files, targetDir)

def symlinkFiles(sourceFiles, targetDir, emptyTargetDirFirst=True):
	"""Populates targetDir with symlinks to all the given files"""

	if os.path.exists(targetDir) and emptyTargetDirFirst:
		shutil.rmtree(targetDir)
	if not os.path.exists(targetDir):
		os.makedirs(targetDir)
	for sourceFile in sourceFiles:
		os.symlink(sourceFile, targetDir + '/' + os.path.basename(sourceFile))

def touchFile(theFile, stamp=None):  # @DontTrace
	"""Touches given file, making sure that its modification date is bumped"""

	if stamp is not None:
		t = time.mktime(stamp.timetuple())
	if os.path.exists(theFile):
		os.utime(theFile, None if stamp is None else (t, t))
	else:
		open(theFile, 'w').close()
		if stamp is not None:
			os.utime(theFile, (t, t))

def storeStringInFile(string, theFile):
	"""Stores the given string in the file with the given name"""

	with codecs.open(theFile, 'w', 'utf-8') as fo:
		fo.write(string)

def readStringFromFile(theFile):
	"""Returns the contents of the file with the given name as a string"""

	with codecs.open(theFile, 'r', 'utf-8') as fo:
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
		sysExit("'" + command + u"' is not available, please install it")

def cmp(a, b):
	return (a > b) - (a < b)

def naturalCompare(left, right):
	"""performs a natural compare between the two given strings - returns:
		-1 if left is lower than right
		 1 if left is higher than right
		 0 if both are equal"""

	convert = lambda text: int(text) if text.isdigit() else text.lower()
	alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
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
			return 1
	elif len(rightElements) < 2:
		return -1

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

def prefixLines(prefix, string):
	"""prefixes each line in the given string by prefix"""
	return '\n'.join('{}{}'.format(prefix, line) for line in string.split('\n'))
