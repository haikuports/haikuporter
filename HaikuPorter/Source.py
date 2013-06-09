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

from HaikuPorter.GlobalConfig import globalConfiguration
from HaikuPorter.Options import getOption
from HaikuPorter.Utils import (check_output, ensureCommandIsAvailable, sysExit, 
							   unpackArchive, warn)

import hashlib
import os
import re
import shutil
from subprocess import check_call


# -- A source archive (or checkout) -------------------------------------------

class Source(object):
	def __init__(self, port, index, uris, localFileName, checksum, sourceDir, 
				 patches):
		self.index = index
		self.uris = uris
		self.localFileName = localFileName
		self.checksum = checksum
		self.patches = patches
		
		if index == '1':
			self.sourceBaseDir = port.sourceBaseDir
		else:
			self.sourceBaseDir = port.sourceBaseDir + '-' + index
		
		if sourceDir:
			self.sourceDir = self.sourceBaseDir + '/' + sourceDir
		else:
			self.sourceDir = self.sourceBaseDir

		# If explicit PATCHES were specified, set our patches list accordingly.
		if self.patches:
			self.patches = [ port.patchesDir + '/' + p for p in self.patches ]
			
		# set local filename from URI, unless specified explicitly
		if not self.localFileName:
			uri = self.uris[0]
			self.localFileName = uri[uri.rindex('/') + 1:]
		if self.localFileName.endswith('#noarchive'):
			self.localFileName = self.localFileName[:-10]

		self.localFile = port.downloadDir + '/' + self.localFileName
		self.localFileIsArchive = True
		self.checkout = None
		
		self.gitEnv = {
			'GIT_COMMITTER_EMAIL': globalConfiguration['PACKAGER_EMAIL'],
			'GIT_COMMITTER_NAME': globalConfiguration['PACKAGER_NAME'],
			'GIT_AUTHOR_EMAIL': globalConfiguration['PACKAGER_EMAIL'],
			'GIT_AUTHOR_NAME': globalConfiguration['PACKAGER_NAME'],
		}


	def download(self, port):
		"""Fetch the source archive or do a checkout"""

		for uri in self.uris:
			# Examine the URI to determine if we need to perform a checkout
			# instead of download
			if re.match('^cvs.*$|^svn.*$|^hg.*$|^git.*$|^bzr.*$|^fossil.*$',
						uri):
				try:
					self._checkout(port, uri)
					return
				except Exception as e:
					warn('Checkout error from %s:\n\t%s\ntrying next location.' 
						 % (uri, str(e)))
					self.checkout = None
					continue

			# The source URI may be a local file path relative to the port
			# directory.
			if not ':' in uri:
				filePath = port.baseDir + '/' + uri
				if not os.path.isfile(filePath):
					print ("SRC_URI %s looks like a local file path, but "
						   + "doesn't refer to a file, trying next location.\n"
						   % uri)
					continue

				self.localFile = filePath
				return

			try:
				if uri.endswith('#noarchive'):
					self.localFileIsArchive = False
				if os.path.isfile(self.localFile):
					print 'Skipping download of ' + self.localFileName
				else:
					# create download dir and cd into it
					downloadDir = os.path.dirname(self.localFile)
					if not os.path.exists(downloadDir):
						os.mkdir(downloadDir)
					os.chdir(downloadDir)

					print '\nDownloading: ' + uri + ' ...'
					ensureCommandIsAvailable('wget')
					args = ['wget', '-c', '--tries=3', '-O', self.localFile, 
							uri]
					if uri.startswith('https://'):
						args.insert(3, '--no-check-certificate')
					check_call(args)

				# successfully downloaded source or it was already there
				return
			except Exception:
				warn('Download error from %s, trying next location.' % uri)

		# failed to fetch source
		sysExit('Failed to download source package from all locations.')

	def validateChecksum(self, port):
		"""Make sure that the MD5-checksum matches the expectations"""

		if self.checksum:
			print 'Validating MD5 checksum of ' + self.localFileName
			h = hashlib.md5()
			f = open(self.localFile, 'rb')
			while True:
				d = f.read(16384)
				if not d:
					break
				h.update(d)
			f.close()
			if h.hexdigest() != self.checksum:
				sysExit('Expected: ' + self.checksum + '\n'
						+ 'Found: ' + h.hexdigest())
		else:
			# The checkout flag only gets set when a source checkout is 
			# performed. If it exists we don't need to warn about the missing 
			# recipe field
			if not port.checkFlag('checkout', self.index):
				warn('No CHECKSUM_MD5 key found in recipe for ' 
					 + self.localFileName)

	def unpackSource(self, port):
		"""Unpack the source archive (into the work directory)"""

		# Skip the unpack step if the source came from a vcs
		if port.checkFlag('checkout', self.index):
			return

		# Check to see if the source archive was already unpacked.
		if port.checkFlag('unpack', self.index) and not getOption('force'):
			print 'Skipping unpack of ' + self.localFileName
			return

		# re-create target directory for this source
		if os.path.exists(self.sourceBaseDir):
			shutil.rmtree(self.sourceBaseDir)
		os.makedirs(self.sourceBaseDir)

		# unpack source archive or simply copy source file
		if not self.localFileIsArchive:
			shutil.copy(self.localFile, self.sourceBaseDir)
		else:
			print 'Unpacking ' + self.localFileName
			unpackArchive(self.localFile, self.sourceBaseDir)

		# automatically try to rename archive folders containing '-':
		if not os.path.exists(self.sourceDir):
			maybeSourceDirName \
				= os.path.basename(self.sourceDir).replace('_', '-')
			maybeSourceDir = (os.path.dirname(self.sourceDir) + '/'
							  + maybeSourceDirName)
			if os.path.exists(maybeSourceDir):
				os.rename(maybeSourceDir, self.sourceDir)

		port.setFlag('unpack', self.index)

	def patch(self, port):
		"""Apply any patches to this source"""

		# Check to see if the source has already been patched.
		if port.checkFlag('patchset', self.index) and not getOption('force'):
			return True

		if getOption('initGitRepo'):
			if not os.path.exists(self.sourceDir + '/.git'):
				# import sources into pristine git repository
				self._initGitRepo()

		if not self.patches:
			return False

		# use a git repository for improved patch handling.
		ensureCommandIsAvailable('git')
		if not os.path.exists(self.sourceDir + '/.git'):
			# import sources into pristine git repository
			self._initGitRepo()
		else:
			# reset existing git repsitory before appling patchset(s) again
			self.reset()

		patched = False
		try:
			# Apply patches
			for patch in self.patches:
				if not os.path.exists(patch):
					sysExit('patch file "' + patch + '" not found.')

				if patch.endswith('.patchset'):
					print 'Applying patchset "%s" ...' % patch
					check_call(['git', 'am', '-3', patch], cwd=self.sourceDir)
				else:
					print 'Applying patch "%s" ...' % patch
					check_call(['git', 'apply', '-p1', '--index', patch], 
							   cwd=self.sourceDir)
					check_call(['git', 'commit', '-q', '-m', 'applying patch %s' 
								% os.path.basename(patch)], 
							   cwd=self.sourceDir, env=self.gitEnv)
				patched = True
		except:
			# Don't leave behind half-patched sources.
			if patched:
				self.reset()
			raise

		if patched:
			port.setFlag('patchset', self.index)
			
		return patched

	def reset(self):
		"""Reset source to original state"""

		check_call(['git', 'reset', '--hard', 'ORIGIN'], cwd=self.sourceDir)
		check_call(['git', 'clean', '-f', '-d'], cwd=self.sourceDir)

	def commitPatchPhase(self):
		"""Commit changes done in patch phase."""

		# see if there are any changes at all
		changes = check_output(['git', 'status', '--porcelain'], 
							   cwd=self.sourceDir)
		if not changes:
			print("Patch function hasn't changed anything for " 
				  + self.localFileName)
			return
		
		print('Committing changes done in patch function for ' 
			  + self.localFileName)
		check_call(['git', 'commit', '-a', '-q', '-m', 'patch function'], 
				   cwd=self.sourceDir, env=self.gitEnv)
		check_call(['git', 'tag', '-f', 'PATCH_FUNCTION', 'HEAD'], 
				   cwd=self.sourceDir)

	def extractPatchset(self, patchSetFilePath, archPatchSetFilePath):
		"""Extract the current set of patches applied to git repository,
		   taking care to not include the programatic changes introduced 
		   during the patch phase"""

		if not os.path.exists(self.sourceDir):
			sysExit("Can't extract patchset for " + self.localFileName 
					+ " as the source directory doesn't exist yet")

		print 'Extracting patchset for ' + self.localFileName
		needToRebase = True
		try:
			# check if the tag 'PATCH_FUNCTION' exists
			with open(os.devnull, "w") as devnull:
				check_call(['git', 'rev-parse', '--verify', 'PATCH_FUNCTION'], 
						   stdout=devnull, stderr=devnull, cwd=self.sourceDir)
		except:
			# no PATCH_FUNCTION tag, so there's nothing to rebase
			needToRebase = False

		if needToRebase:			
			# the tag exists, so we drop the respective commit
			check_call(['git', 'rebase', '-q', '--onto', 'PATCH_FUNCTION^', 
						'PATCH_FUNCTION', 'master'], cwd=self.sourceDir)
			
		with open(patchSetFilePath, 'w') as patchSetFile:
			check_call(['git', 'format-patch', '-kp', '--stdout', 'ORIGIN'], 
					   stdout=patchSetFile, cwd=self.sourceDir)
			
		if needToRebase:			
			# put PATCH_FUNCTION back in
			check_call(['git', 'rebase', '-q', 'PATCH_FUNCTION', 'master'], 
					   cwd=self.sourceDir)

		# warn if there's a correpsonding arch-specific patchset file
		if os.path.exists(archPatchSetFilePath):
			warn('arch-specific patchset file %s requires manual update' 
				 % os.path.basename(archPatchSetFilePath))
			
		# if there's a corresponding patch file, remove it, as we now have
		# the patchset
		patchFilePath = patchSetFilePath[:-3]
		if os.path.exists(patchFilePath):
			warn('removing obsolete patch file ' 
				 + os.path.basename(patchFilePath))
			os.remove(patchFilePath)
		# if there's a corresponding diff file, remove it, as we now have
		# the patchset
		diffFilePath = patchFilePath[:-6] + '.diff'
		if os.path.exists(diffFilePath):
			warn('removing obsolete diff file ' 
				 + os.path.basename(diffFilePath))
			os.remove(diffFilePath)
			
	def adjustToChroot(self, port):
		"""Adjust directories to chroot()-ed environment"""
		
		self.localFile = None

		# adjust all relevant directories
		pathLengthToCut = len(port.workDir)
		self.sourceBaseDir = self.sourceBaseDir[pathLengthToCut:]
		self.sourceDir = self.sourceDir[pathLengthToCut:]
				
	def _checkout(self, port, uri):
		"""Parse the URI and execute the appropriate command to check out the
		   source."""

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

		self.checkout = {
			'type': type,
			'uri': realUri,
			'rev': rev,
		}

		if port.checkFlag('checkout', self.index) and not getOption('force'):
			print 'Source already checked out. Skipping ...'
			return

		# If the source-base dir exists we need to clean it out
		if os.path.exists(self.sourceBaseDir):
			shutil.rmtree(self.sourceBaseDir)
		os.makedirs(self.sourceBaseDir)

		print 'Source checkout: ' + uri

		# Set the name of the directory to check out sources into
		checkoutDir = self.sourceBaseDir + '/' + port.versionedName

		# Start building the command to perform the checkout
		if type == 'cvs':
			# Chop off the leading cvs:// part of the uri
			realUri = realUri[realUri.index('cvs://') + 6:]

			# Extract the cvs module from the uri and remove it from real_uri
			module = realUri[realUri.rfind('/') + 1:]
			realUri = realUri[:realUri.rfind('/')]
			ensureCommandIsAvailable('cvs')
			checkoutCommand = 'cvs -d' + realUri + ' co -P'
			if rev:
				# For CVS 'rev' may specify a date or a revision/tag name. If it
				# looks like a date, we assume it is one.
				dateRegExp = re.compile('^\d{1,2}/\d{1,2}/\d{2,4}$')
				if dateRegExp.match(rev):
					checkoutCommand += ' -D' + rev
				else:
					checkoutCommand += ' -r' + rev
			checkoutCommand += ' -d ' + checkoutDir + ' ' + module
		elif type == 'svn':
			ensureCommandIsAvailable('svn')
			checkoutCommand \
				= 'svn co --non-interactive --trust-server-cert'
			if rev:
				checkoutCommand += ' -r ' + rev
			checkoutCommand += ' ' + realUri + ' ' + checkoutDir
		elif type == 'hg':
			ensureCommandIsAvailable('hg')
			checkoutCommand = 'hg clone'
			if rev:
				checkoutCommand += ' -r ' + rev
			checkoutCommand += ' ' + realUri + ' ' + checkoutDir
		elif type == 'bzr':
			# http://doc.bazaar.canonical.com/bzr-0.10/bzr_man.htm#bzr-branch-from-location-to-location
			ensureCommandIsAvailable('bzr')
			checkoutCommand = 'bzr checkout --lightweight'
			if rev:
				checkoutCommand += ' -r ' + rev
			checkoutCommand += ' ' + realUri + ' ' + checkoutDir
		elif type == 'fossil':
			# http://fossil-scm.org/index.html/doc/trunk/www/quickstart.wiki
			if os.path.exists(checkoutDir + '.fossil'):
				shutil.rmtree(checkoutDir + '.fossil')
			ensureCommandIsAvailable('fossil')
			checkoutCommand = ('fossil clone ' + realUri 
							   + ' ' + checkoutDir + '.fossil '
							   + '&& mkdir -p ' + checkoutDir + ' '
							   + '&& fossil open ' + checkoutDir + '.fossil')
			if rev:
				checkoutCommand += ' ' + rev
		elif type == 'git':
			ensureCommandIsAvailable('git')
			self.checkout['type'] = 'git'
			if rev:
				checkoutCommand = (('''
					set -e
					git clone -n %s %s
					cd %s
					if git branch | grep -q '* haikuport'; then
						# point HEAD to something else than the 'haikuport'
						# branch, as we are going to try and update that branch
						# with the following checkout, which would fail if
						# 'haikuport' is the current branch
						git symbolic-ref HEAD refs/origin/HEAD
					fi
					echo "checking out tree for %s ..."
					git checkout -B haikuport -q %s''')
					% (realUri, checkoutDir, checkoutDir, rev, rev))
			else:
				checkoutCommand = 'git clone %s %s' % (realUri, checkoutDir)
			checkoutCommand += '\ngit tag -f ORIGIN'
		else:
			sysExit("repository type '" + type + "' is not supported")

		check_call(checkoutCommand, shell=True, cwd=self.sourceBaseDir)

		# Set the 'checkout' flag to signal that the checkout is complete
		port.setFlag('checkout', self.index)

	def _initGitRepo(self):
		"""Import sources into git repository"""

		ensureCommandIsAvailable('git')
		check_call(['git', 'init'], cwd=self.sourceDir)
		check_call(['git', 'add', '.'], cwd=self.sourceDir)
		check_call(['git', 'commit', '-m', 'import', '-q'], 
				   cwd=self.sourceDir, env=self.gitEnv)
		check_call(['git', 'tag', 'ORIGIN'], cwd=self.sourceDir)
