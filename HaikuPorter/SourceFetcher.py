# -*- coding: utf-8 -*-
# copyright 2007-2011 Brecht Machiels
# copyright 2009-2010 Chris Roberts
# copyright 2009-2011 Scott McCreary
# copyright 2009 Alexander Deynichenko
# copyright 2009 HaikuBot (aka RISC)
# copyright 2010-2011 Jack Laxson (Jrabbit)
# copyright 2011 Ingo Weinhold
# copyright 2013 Oliver Tappe

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Utils import (ensureCommandIsAvailable, sysExit, unpackArchive)

import os
import re
import shutil
from subprocess import check_call


# -----------------------------------------------------------------------------

def parseCheckoutUri(uri):
	"""Parse the given checkout URI and return a 3-tuple with type, real URI
	   and revision."""

	# Attempt to parse a URI with a + in it. ex: hg+http://blah
	# If it doesn't find the 'type' it should extract 'real_uri' and 'rev'
	m = re.match('^((?P<type>\w*)\+)?(?P<realUri>.+?)(#(?P<rev>.+))?$', uri)
	if not m or not m.group('realUri'):
		sysExit("Couldn't parse repository URI " + uri)

	type = m.group('type')
	realUri = m.group('realUri')
	rev = m.group('rev')

	# Attempt to parse a URI without a + in it. ex: svn://blah
	if not type:
		m = re.match("^(\w*).*$", realUri)
		if m:
			type = m.group(1)

	if not type:
		sysExit("Couldn't parse repository type from URI " + realUri)

	return (type, realUri, rev)

# -----------------------------------------------------------------------------

def unpackCheckoutWithTar(checkoutDir, sourceDir, subdir):
	"""Use 'tar' to export the sources from the checkout into the source dir"""

	if subdir:
		command = ('tar -c -C "%s" --exclude-vcs | tar -x -C "%s"' 
				   % (subdir, sourceDir))
	else:
		command = 'tar -c --exclude-vcs . | tar -x -C "%s"' % sourceDir
	check_call(command, cwd=checkoutDir, shell=True)

# -- Fetches sources via bzr --------------------------------------------------

class SourceFetcherForBazaar(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)
		
	def fetch(self):
		ensureCommandIsAvailable('bzr')
		command = 'bzr checkout --lightweight'
		if self.rev:
			command += ' -r ' + self.rev
		command += ' ' + self.uri + ' ' + self.fetchTarget
		check_call(command, shell=True)

	def unpack(self, sourceDir, subdir):
		unpackCheckoutWithTar(self.fetchTarget, sourceDir, subdir)

# -- Fetches sources via cvs --------------------------------------------------

class SourceFetcherForCvs(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, uri, self.rev) = parseCheckoutUri(uri)
		
		# chop the leading 'cvs://' of the URI, then split off the module
		(self.uri, self.module) = uri[6:].rsplit('/', 1)
		
	def fetch(self):
		baseDir = os.path.dirname(self.fetchTarget)

		ensureCommandIsAvailable('cvs')
		command = 'cvs -d' + self.uri + ' co -P'
		if self.rev:
			# self.rev may specify a date or a revision/tag name. If it
			# looks like a date, we assume it is one.
			dateRegExp = re.compile('^\d{1,2}/\d{1,2}/\d{2,4}$')
			if dateRegExp.match(self.rev):
				command += ' -D' + self.rev
			else:
				command += ' -r' + self.rev
		command += ' ' + self.module
		check_call(command, shell=True, cwd=baseDir)

	def unpack(self, sourceDir, subdir):
		unpackCheckoutWithTar(self.fetchTarget, sourceDir, subdir)

# -- Fetches sources via wget -------------------------------------------------

class SourceFetcherForDownload(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.uri = uri
		self.sourceShouldBeValidated = True
		
	def fetch(self):
		downloadDir = os.path.dirname(self.fetchTarget)
		os.chdir(downloadDir)
		ensureCommandIsAvailable('wget')
		args = ['wget', '-c', '--tries=3', '-O', self.fetchTarget, self.uri]
		if self.uri.startswith('https://'):
			args.insert(3, '--no-check-certificate')
		check_call(args)

	def unpack(self, sourceDir, subdir):
		if self.uri.endswith('#noarchive'):
			if os.path.isdir(self.fetchTarget):
				shutil.copytree(self.fetchTarget, sourceDir, symlinks=True)
			else:
				shutil.copy(self.fetchTarget, sourceDir)
		else:
			unpackArchive(self.fetchTarget, os.path.dirname(sourceDir))

# -- Fetches sources via fossil -----------------------------------------------

class SourceFetcherForFossil(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)
		
	def fetch(self):
		ensureCommandIsAvailable('fossil')
		fossilDir = self.fetchTarget + '.fossil'
		if os.path.exists(fossilDir):
			shutil.rmtree(fossilDir)
		command = ('fossil clone ' + self.uri + ' ' + fossilDir
				   + ' && fossil open ' + fossilDir)
		if self.rev:
			command += ' ' + self.rev
		check_call(command, shell=True)

	def unpack(self, sourceDir, subdir):
		unpackCheckoutWithTar(self.fetchTarget, sourceDir, subdir)

# -- Fetches sources via git --------------------------------------------------

class SourceFetcherForGit(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)
		
	def fetch(self):
		ensureCommandIsAvailable('git')
		command = 'git clone -n %s %s' % (self.uri, self.fetchTarget)
		check_call(command, shell=True)

	def unpack(self, sourceDir, subdir):
		if subdir:
			command = ('git archive HEAD "%s" | tar -x -C "%s"' 
					   % (subdir, sourceDir))
		else:
			command = 'git archive HEAD | tar -x -C "%s"' % sourceDir
		check_call(command, shell=True, cwd=self.fetchTarget)

		if subdir:
			# move everything in subdir directly into source-dir
			command = 'mv %s/* . && rm -r %s' % (subdir, subdir)
			check_call(command, shell=True, cwd=sourceDir)

# -- Fetches sources from local disk ------------------------------------------

class SourceFetcherForLocalFile(object):
	# TODO; this implementation is untested, so it may require fixing
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

	def unpack(self, sourceDir, subdir):
		if self.uri.endswith('#noarchive'):
			if os.path.isdir(self.fetchTarget):
				shutil.copytree(self.fetchTarget, sourceDir, symlinks=True)
			else:
				shutil.copy(self.fetchTarget, sourceDir)
		else:
			unpackArchive(self.fetchTarget, os.path.dirname(sourceDir))

# -- Fetches sources via hg ---------------------------------------------------

class SourceFetcherForMercurial(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)
		
	def fetch(self):
		ensureCommandIsAvailable('hg')
		command = 'hg clone'
		if self.rev:
			command += ' -r ' + self.rev
		command += ' ' + self.uri + ' ' + self.fetchTarget
		check_call(command, shell=True)

	def unpack(self, sourceDir, subdir):
		if subdir:
			command = 'hg archive -I "%s" -t files "%s"' % (subdir, sourceDir)
		else:
			command = 'hg archive -t files "%s"' % sourceDir
		check_call(command, shell=True, cwd=self.fetchTarget)

		if subdir:
			# move everything in subdir directly into source-dir
			command = 'mv %s/* . && rm -r %s' % (subdir, subdir)
			check_call(command, shell=True, cwd=sourceDir)

# -- Fetches sources via svn --------------------------------------------------

class SourceFetcherForSubversion(object):
	def __init__(self, uri, fetchTarget):
		self.fetchTarget = fetchTarget
		self.sourceShouldBeValidated = False

		(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)
		
	def fetch(self):
		ensureCommandIsAvailable('svn')
		command = 'svn co --non-interactive --trust-server-cert'
		if self.rev:
			command += ' -r ' + self.rev
		command += ' ' + self.uri + ' ' + self.fetchTarget
		check_call(command, shell=True)

	def unpack(self, sourceDir, subdir):
		unpackCheckoutWithTar(self.fetchTarget, sourceDir, subdir)

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
	elif lowerUri.startswith('svn'):
		return SourceFetcherForSubversion(uri, fetchTarget)
	elif ':' not in lowerUri:
		return SourceFetcherForLocalFile(uri, fetchTarget)
	else:
		sysExit('The protocol of SRC_URI %s is unsupported, sorry.' % uri)
