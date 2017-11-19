# -*- coding: utf-8 -*-
#
# Copyright 2007-2011 Brecht Machiels
# Copyright 2009-2010 Chris Roberts
# Copyright 2009-2011 Scott McCreary
# Copyright 2009 Alexander Deynichenko
# Copyright 2009 HaikuBot (aka RISC)
# Copyright 2010-2011 Jack Laxson (Jrabbit)
# Copyright 2011 Ingo Weinhold
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .Configuration import Configuration
from .Utils import ensureCommandIsAvailable, info, sysExit, unpackArchive, warn

import os
import re
import shutil
from subprocess import CalledProcessError, check_output, PIPE, Popen, STDOUT
import time


# -----------------------------------------------------------------------------

def parseCheckoutUri(uri):
	"""Parse the given checkout URI and return a 3-tuple with type, real URI
	   and revision."""

	# Attempt to parse a URI with a + in it. ex: hg+http://blah
	# If it doesn't find the 'type' it should extract 'real_uri' and 'rev'
	m = re.match('^((?P<type>\w*)\+)?(?P<realUri>.+?)(#(?P<rev>.+))?$', uri)
	if not m or not m.group('realUri'):
		sysExit(u"Couldn't parse repository URI " + uri)

	uriType = m.group('type')
	realUri = m.group('realUri')
	rev = m.group('rev')

	# Attempt to parse a URI without a + in it. ex: svn://blah
	if not uriType:
		m = re.match("^(\w*).*$", realUri)
		if m:
			uriType = m.group(1)

	if not uriType:
		sysExit(u"Couldn't parse repository type from URI " + realUri)

	return (uriType, realUri, rev)

# -----------------------------------------------------------------------------

def unpackCheckoutWithTar(checkoutDir, sourceBaseDir, sourceSubDir, foldSubDir):
	"""Use 'tar' to export the sources from the checkout into the source dir"""

	sourceDir = sourceBaseDir + '/' + sourceSubDir \
		if sourceSubDir else sourceBaseDir
	if foldSubDir:
		command = ('tar -c -C "%s" --exclude-vcs | tar -x -C "%s"'
				   % (foldSubDir, sourceDir))
	else:
		command = 'tar -c --exclude-vcs . | tar -x -C "%s"' % sourceDir
	output = check_output(command, cwd=checkoutDir, shell=True)
	info(output)

	if foldSubDir:
		foldSubdirIntoSourceDir(foldSubDir, sourceDir)

# -----------------------------------------------------------------------------

def unpackFile(uri, fetchTarget, sourceBaseDir, sourceSubDir, foldSubDir):
	"""Unpack archive file (or copy non-archive) into sourceDir"""

	sourceDir = sourceBaseDir + '/' + sourceSubDir \
		if sourceSubDir else sourceBaseDir
	if uri.endswith('#noarchive'):
		if os.path.isdir(fetchTarget):
			shutil.copytree(fetchTarget, sourceDir, symlinks=True)
		else:
			shutil.copy(fetchTarget, sourceDir)
	else:
		actualSubDir = sourceSubDir
		if actualSubDir:
			if foldSubDir:
				actualSubDir += '/' + foldSubDir
		else:
			actualSubDir = foldSubDir
		unpackArchive(fetchTarget, sourceBaseDir, actualSubDir)
		if foldSubDir:
			foldSubdirIntoSourceDir(foldSubDir, sourceDir)

# -----------------------------------------------------------------------------

def foldSubdirIntoSourceDir(subdir, sourceDir):
	"""Move contents of subdir into sourceDir and remove subdir"""

	# rename subdir to something unique in order to avoid potential problems
	# if it contains an identically named file or folder.
	fullSubdirPath = sourceDir + '/subdir-to-be-folded-by-haikuporter'
	os.rename(sourceDir + '/' + subdir, fullSubdirPath)
	# now move all contents from the subdir into the source directory
	for fileName in os.listdir(fullSubdirPath):
		os.rename(fullSubdirPath + '/' + fileName, sourceDir + '/' + fileName)
	os.removedirs(fullSubdirPath)

# -- Fetches sources via bzr --------------------------------------------------

class SourceFetcherForBazaar(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)

	def fetch(self):
		if not Configuration.shallAllowUnsafeSources():
			sysExit(u'Downloading from unsafe sources is disabled in ' +
					u'haikuports.conf!')

		warn("UNSAFE SOURCES ARE BAD AND SHOULD NOT BE USED IN PRODUCTION")
		warn("PLEASE MOVE TO A STATIC ARCHIVE DOWNLOAD WITH CHECKSUM ASAP!")

		ensureCommandIsAvailable('bzr')
		command = 'bzr checkout --lightweight'
		if self.rev:
			command += ' -r ' + self.rev
		command += ' ' + self.uri + ' ' + self.fetchTarget
		output = check_output(command, shell=True, stderr=STDOUT)
		info(output)

	def updateToRev(self, rev):
		warn(u"Updating of a Bazaar repository to a specific revision has "
			 u"not been implemented yet, sorry")

	def unpack(self, sourceBaseDir, sourceSubDir, foldSubDir):
		unpackCheckoutWithTar(self.fetchTarget, sourceBaseDir, sourceSubDir,
			foldSubDir)

# -- Fetches sources via cvs --------------------------------------------------

class SourceFetcherForCvs(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, uri, self.rev) = parseCheckoutUri(uri)

		# chop the leading 'cvs://' of the URI, then split off the module
		(self.uri, self.module) = uri[6:].rsplit('/', 1)

	def fetch(self):
		if not Configuration.shallAllowUnsafeSources():
			sysExit(u'Downloading from unsafe sources is disabled in ' +
					u'haikuports.conf!')

		warn("UNSAFE SOURCES ARE BAD AND SHOULD NOT BE USED IN PRODUCTION")
		warn("PLEASE MOVE TO A STATIC ARCHIVE DOWNLOAD WITH CHECKSUM ASAP!")

		baseDir = os.path.dirname(self.fetchTarget)

		ensureCommandIsAvailable('cvs')
		command = 'cvs -d' + self.uri + ' co -P'
		if self.rev:
			# self.rev may specify a date or a revision/tag name. If it
			# looks like a date, we assume it is one.
			dateRegExp = re.compile('^\d{1,2}/\d{1,2}/\d{2,4}$|^\d{4}-\d{2}-\d{2}$')
			if dateRegExp.match(self.rev):
				command += ' -D' + self.rev
			else:
				command += ' -r' + self.rev
		command += ' "%s"' % self.module
		output = check_output(command, shell=True, cwd=baseDir, stderr=STDOUT)
		info(output)

	def updateToRev(self, rev):
		warn(u"Updating of a CVS repository to a specific revision has "
			 u"not been implemented yet, sorry")

	def unpack(self, sourceBaseDir, sourceSubDir, foldSubDir):
		unpackCheckoutWithTar(self.fetchTarget, sourceBaseDir, sourceSubDir,
			foldSubDir)

# -- Fetches sources via wget -------------------------------------------------

class SourceFetcherForDownload(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.uri = uri
		self.sourceShouldBeValidated = True

	def fetch(self):
		downloadDir = os.path.dirname(self.fetchTarget)
		ensureCommandIsAvailable('wget')
		mirror = ''
		if 'sourceforge.net/' in self.uri or '.sf.net/' in self.uri:
			if Configuration.getSourceforgeMirror():
				mirror = '?use_mirror=' + Configuration.getSourceforgeMirror()

		args = [ 'wget', '-c', '--timeout=10', '-O', self.fetchTarget,
			self.uri + mirror]

		code = 0
		for tries in range(0, 3):
			process = Popen(args, cwd=downloadDir, stdout=PIPE, stderr=STDOUT)
			for line in iter(process.stdout.readline, b''):
				info(line[:-1])
			process.stdout.close()
			code = process.wait()
			if code in (0, 2, 6, 8):
				# 0: success
				# 2: parse error of command line
				# 6: auth failure
				# 8: error response from server
				break

			time.sleep(3)

		if code:
			raise CalledProcessError(code, args)

	def updateToRev(self, rev):
		pass

	def unpack(self, sourceBaseDir, sourceSubDir, foldSubDir):
		unpackFile(self.uri, self.fetchTarget, sourceBaseDir, sourceSubDir,
			foldSubDir)

# -- Fetches sources via fossil -----------------------------------------------

class SourceFetcherForFossil(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)

	def fetch(self):
		if not Configuration.shallAllowUnsafeSources():
			sysExit(u'Downloading from unsafe sources is disabled in ' +
					u'haikuports.conf!')

		warn("UNSAFE SOURCES ARE BAD AND SHOULD NOT BE USED IN PRODUCTION")
		warn("PLEASE MOVE TO A STATIC ARCHIVE DOWNLOAD WITH CHECKSUM ASAP!")

		ensureCommandIsAvailable('fossil')
		fossilDir = self.fetchTarget + '.fossil'
		if os.path.exists(fossilDir):
			shutil.rmtree(fossilDir)
		command = ('fossil clone ' + self.uri + ' ' + fossilDir
				   + ' && fossil open ' + fossilDir)
		if self.rev:
			command += ' ' + self.rev
		output = check_output(command, shell=True, stderr=STDOUT)
		info(output)

	def updateToRev(self, rev):
		warn(u"Updating of a Fossil repository to a specific revision has "
			 u"not been implemented yet, sorry")

	def unpack(self, sourceBaseDir, sourceSubDir, foldSubDir):
		unpackCheckoutWithTar(self.fetchTarget, sourceBaseDir, sourceSubDir,
			foldSubDir)

# -- Fetches sources via git --------------------------------------------------

class SourceFetcherForGit(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)
		if not self.rev:
			self.rev = 'HEAD'

	def fetch(self):
		if not Configuration.shallAllowUnsafeSources():
			sysExit(u'Downloading from unsafe sources is disabled in ' +
					u'haikuports.conf!')

		warn("UNSAFE SOURCES ARE BAD AND SHOULD NOT BE USED IN PRODUCTION")
		warn("PLEASE MOVE TO A STATIC ARCHIVE DOWNLOAD WITH CHECKSUM ASAP!")

		ensureCommandIsAvailable('git')
		command = 'git clone --bare %s %s' % (self.uri, self.fetchTarget)
		output = check_output(command, shell=True, stderr=STDOUT)
		info(output)

	def updateToRev(self, rev):
		ensureCommandIsAvailable('git')

		self.rev = rev
		command = 'git rev-list --max-count=1 %s &>/dev/null' % self.rev
		try:
			output = check_output(command, shell=True, cwd=self.fetchTarget)
			info(output)
		except:
			print 'trying to fetch revision %s from upstream' % self.rev
			command = "git branch | cut -c3-"
			branches = check_output(command, shell=True,
									cwd=self.fetchTarget, stderr=STDOUT).splitlines()
			for branch in branches:
				command = 'git fetch origin %s:%s' % (branch, branch)
				print command
				output = check_output(command, shell=True, cwd=self.fetchTarget)
				info(output)
			# ensure that the revision really is available now
			command = 'git rev-list --max-count=1 %s &>/dev/null' % self.rev
			output = check_output(command, shell=True, cwd=self.fetchTarget)
			info(output)

	def unpack(self, sourceBaseDir, sourceSubDir, foldSubDir):
		sourceDir = sourceBaseDir + '/' + sourceSubDir \
			if sourceSubDir else sourceBaseDir
		if foldSubDir:
			command = ('git archive %s "%s" | tar -x -C "%s"'
					   % (self.rev, foldSubDir, sourceDir))
		else:
			command = 'git archive %s | tar -x -C "%s"' % (self.rev, sourceDir)
		output = check_output(command, shell=True, cwd=self.fetchTarget)
		info(output)

		if foldSubDir:
			foldSubdirIntoSourceDir(foldSubDir, sourceDir)

# -- Fetches sources from local disk ------------------------------------------

class SourceFetcherForLocalFile(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.uri = uri
		self.sourceShouldBeValidated = False

	def fetch(self):
		# just symlink the local file to fetchTarget (if it exists)
		portBaseDir = os.path.dirname(os.path.dirname(self.fetchTarget))
		localFile = portBaseDir + '/' + self.uri
		if not os.path.isfile(localFile):
			raise NameError("source %s doesn't exist" % localFile)
		os.symlink(localFile, self.fetchTarget)

	def updateToRev(self, rev):
		pass

	def unpack(self, sourceBaseDir, sourceSubDir, foldSubDir):
		unpackFile(self.uri, self.fetchTarget, sourceBaseDir, sourceSubDir,
			foldSubDir)

# -- Fetches sources via hg ---------------------------------------------------

class SourceFetcherForMercurial(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)

	def fetch(self):
		if not Configuration.shallAllowUnsafeSources():
			sysExit(u'Downloading from unsafe sources is disabled in ' +
					u'haikuports.conf!')

		warn("UNSAFE SOURCES ARE BAD AND SHOULD NOT BE USED IN PRODUCTION")
		warn("PLEASE MOVE TO A STATIC ARCHIVE DOWNLOAD WITH CHECKSUM ASAP!")
		ensureCommandIsAvailable('hg')
		command = 'hg clone'
		if self.rev:
			command += ' -r ' + self.rev
		command += ' ' + self.uri + ' ' + self.fetchTarget
		output = check_output(command, shell=True, stderr=STDOUT)
		info(output)

	def updateToRev(self, rev):
		ensureCommandIsAvailable('hg')
		self.rev = rev

	def unpack(self, sourceBaseDir, sourceSubDir, foldSubDir):
		if not self.rev:
			self.rev = 'tip'

		sourceDir = sourceBaseDir + '/' + sourceSubDir \
			if sourceSubDir else sourceBaseDir
		if foldSubDir:
			command = 'hg archive -r %s -I "%s" -t files "%s"' \
				% (self.rev, foldSubDir, sourceDir)
		else:
			command = 'hg archive -r %s -t files "%s"' % (self.rev, sourceDir)
		output = check_output(command, shell=True, cwd=self.fetchTarget)
		info(output)

		if foldSubDir:
			foldSubdirIntoSourceDir(foldSubDir, sourceDir)

# -- Fetches sources from source package --------------------------------------

class SourceFetcherForSourcePackage(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.uri = uri
		self.sourceShouldBeValidated = False
		self.sourcePackagePath = self.uri[4:]

	def fetch(self):
		pass

	def updateToRev(self, rev):
		pass

	def unpack(self, sourceBaseDir, sourceSubDir, foldSubDir):
		sourceDir = sourceBaseDir + '/' + sourceSubDir \
			if sourceSubDir else sourceBaseDir

		sourcePackageName = os.path.basename(self.sourcePackagePath)
		(name, version, revision, unused) = sourcePackageName.split('-')
		# determine port name by dropping '_source' or '_source_rigged'
		if name.endswith('_source_rigged'):
			name = name[:-14]
		elif name.endswith('_source'):
			name = name[:-7]
		relativeSourcePath = ('develop/sources/%s-%s-%s/%s'
							  % (name, version, revision,
								 os.path.basename(sourceBaseDir)))

		output = check_output([Configuration.getPackageCommand(), 'extract',
					'-C', sourceDir, self.sourcePackagePath,
					relativeSourcePath], stderr=STDOUT)
		info(output)
		foldSubdirIntoSourceDir(relativeSourcePath, sourceDir)

# -- Fetches sources via svn --------------------------------------------------

class SourceFetcherForSubversion(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)

	def fetch(self):
		if not Configuration.shallAllowUnsafeSources():
			sysExit(u'Downloading from unsafe sources is disabled in ' +
					u'haikuports.conf!')

		ensureCommandIsAvailable('svn')
		command = 'svn co --non-interactive --trust-server-cert'
		if self.rev:
			command += ' -r ' + self.rev
		command += ' ' + self.uri + ' ' + self.fetchTarget
		output = check_output(command, shell=True, stderr=STDOUT)
		info(output)

	def updateToRev(self, rev):
		warn(u"Updating of a Subversion repository to a specific revision has "
			 u"not been implemented yet, sorry")

	def unpack(self, sourceBaseDir, sourceSubDir, foldSubDir):
		unpackCheckoutWithTar(self.fetchTarget, sourceBaseDir, sourceSubDir,
			foldSubDir)

# -- source fetcher factory function for given URI ----------------------------

def createSourceFetcher(uri, fetchTarget):
	"""Creates an appropriate source fetcher for the given URI"""

	lowerUri = uri.lower()
	if lowerUri.startswith('bzr'):
		return SourceFetcherForBazaar(uri, fetchTarget)
	elif lowerUri.startswith('cvs'):
		return SourceFetcherForCvs(uri, fetchTarget)
	elif lowerUri.startswith('fossil'):
		return SourceFetcherForFossil(uri, fetchTarget)
	elif lowerUri.startswith('git'):
		return SourceFetcherForGit(uri, fetchTarget)
	elif lowerUri.startswith('hg'):
		return SourceFetcherForMercurial(uri, fetchTarget)
	elif lowerUri.startswith('http') or lowerUri.startswith('ftp'):
		return SourceFetcherForDownload(uri, fetchTarget)
	elif lowerUri.startswith('pkg:'):
		return SourceFetcherForSourcePackage(uri, fetchTarget)
	elif lowerUri.startswith('svn'):
		return SourceFetcherForSubversion(uri, fetchTarget)
	elif lowerUri.startswith('file://'):
		return SourceFetcherForLocalFile(uri[7:], fetchTarget)
	elif ':' not in lowerUri:
		return SourceFetcherForLocalFile(uri, fetchTarget)
	else:
		sysExit(u'The protocol of SOURCE_URI %s is unsupported, sorry.' % uri)
