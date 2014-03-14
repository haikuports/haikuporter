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

from HaikuPorter.Configuration import Configuration
from HaikuPorter.Options import getOption
from HaikuPorter.SourceFetcher import (createSourceFetcher,
									   foldSubdirIntoSourceDir, parseCheckoutUri)
from HaikuPorter.Utils import (check_output, ensureCommandIsAvailable,
							   readStringFromFile, storeStringInFile, sysExit,
							   warn)

import hashlib
import os
import shutil
from subprocess import check_call


# -- A source archive (or checkout) -------------------------------------------

class Source(object):
	def __init__(self, port, index, uris, fetchTargetName, checksums,
				 sourceDir, patches, additionalFiles):
		self.index = index
		self.uris = uris
		self.fetchTargetName = fetchTargetName
		self.checksums = checksums
		self.patches = patches
		self.additionalFiles = additionalFiles

		if index == '1':
			self.sourceBaseDir = port.sourceBaseDir
		else:
			self.sourceBaseDir = port.sourceBaseDir + '-' + index

		if sourceDir:
			index = sourceDir.find('/')
			if index > 0:
				self.sourceExportSubdir = sourceDir[index + 1:]
				sourceDir = sourceDir[:index]
			else:
				self.sourceExportSubdir = None
			self.sourceSubDir = sourceDir
			self.sourceDir = self.sourceBaseDir + '/' + sourceDir
		else:
			self.sourceDir = self.sourceBaseDir
			self.sourceSubDir = None
			self.sourceExportSubdir = None

		# PATCHES refers to patch files relative to the patches directory,
		# make those absolute paths.
		if self.patches and port.patchesDir:
			self.patches = [
				port.patchesDir + '/' + patch for patch in self.patches
			]

		# ADDITIONAL_FILES refers to the files relative to the additional-files
		# directory, make those absolute paths.
		if self.additionalFiles:
			self.additionalFiles = [
				port.additionalFilesDir + '/' + additionalFile
				for additionalFile in self.additionalFiles
			]

		# determine filename of first URI
		uriFileName = self.uris[0]
		uriExtension = ''
		hashPos = uriFileName.find('#')
		if hashPos >= 0:
			uriExtension = uriFileName[hashPos:]
			uriFileName = uriFileName[:hashPos]
		uriFileName = uriFileName[uriFileName.rindex('/') + 1:]

		# set local filename from URI, unless specified explicitly
		if not self.fetchTargetName:
			self.fetchTargetName = uriFileName
			
		downloadMirror = Configuration.getDownloadMirror()
		if downloadMirror:
			# add fallback URI using a general source tarball mirror (some 
			# original source sites aren't very reliable)
			self.uris.append(downloadMirror + '/' + uriFileName + uriExtension)

		self.sourceFetcher = None
		self.fetchTarget = port.downloadDir + '/' + self.fetchTargetName
		self.fetchTargetIsArchive = True

		self.gitEnv = {
			'GIT_COMMITTER_EMAIL': Configuration.getPackagerEmail(),
			'GIT_COMMITTER_NAME': Configuration.getPackagerName(),
			'GIT_AUTHOR_EMAIL': Configuration.getPackagerEmail(),
			'GIT_AUTHOR_NAME': Configuration.getPackagerName(),
		}

	def fetch(self, port):
		"""Fetch the source from one of the URIs given in the recipe.
		   If the sources have already been fetched, setup an appropriate
		   source fetcher object
		"""

		# create download dir
		downloadDir = os.path.dirname(self.fetchTarget)
		if not os.path.exists(downloadDir):
			os.mkdir(downloadDir)

		# check if we've already downloaded the sources
		uriFile = self.fetchTarget + '.uri'
		if os.path.exists(self.fetchTarget):
			if os.path.exists(uriFile):
				# create a source fetcher corresponding to the base URI found
				# in the uri file and update to a different revision, if needed
				storedUri = readStringFromFile(uriFile)
				(unusedType, storedBaseUri, storedRev) \
					= parseCheckoutUri(storedUri)

				for uri in self.uris:
					(unusedType, baseUri, rev) = parseCheckoutUri(uri)
					if baseUri == storedBaseUri:
						self.sourceFetcher \
							= createSourceFetcher(uri, self.fetchTarget)
						if rev != storedRev:
							self.sourceFetcher.updateToRev(rev)
							storeStringInFile(uri, self.fetchTarget + '.uri')
							port.unsetFlag('unpack', self.index)
							port.unsetFlag('patchset', self.index)
						else:
							print ('Skipping download of source for '
								   + self.fetchTargetName)
						break
				else:
					warn("Stored SRC_URI is no longer in recipe, automatic "
						 "repository update won't work")
					self.sourceFetcher \
						= createSourceFetcher(storedUri, self.fetchTarget)

				return
			else:
				# Remove the fetch target, as it isn't complete
				if os.path.isdir(self.fetchTarget):
					shutil.rmtree(self.fetchTarget)
				else:
					os.remove(self.fetchTarget)

		# download the sources
		for uri in self.uris:
			try:
				print '\nDownloading: ' + uri + ' ...'
				sourceFetcher = createSourceFetcher(uri, self.fetchTarget)
				sourceFetcher.fetch()

				# ok, fetching the source was successful, we keep the source
				# fetcher and store the URI that the source came from for
				# later runs
				self.sourceFetcher = sourceFetcher
				storeStringInFile(uri, self.fetchTarget + '.uri')
				return
			except Exception as e:
				if uri != self.uris[-1]:
					warn(('Unable to fetch source from %s (error: %s), '
						  + 'trying next location.') % (uri, e))
				else:
					warn(('Unable to fetch source from %s (error: %s)') 
						 % (uri, e))

		# failed to fetch source
		sysExit('Failed to fetch source from all known locations.')

	def unpack(self, port):
		"""Unpack the source into the source directory"""

		# Check to see if the source was already unpacked.
		if port.checkFlag('unpack', self.index) and not getOption('force'):
			print 'Skipping unpack of ' + self.fetchTargetName
			return

		# re-create source directory
		if os.path.exists(self.sourceBaseDir):
			print 'Cleaning source dir for ' + self.fetchTargetName
			shutil.rmtree(self.sourceBaseDir)
		os.makedirs(self.sourceDir)

		print 'Unpacking source of ' + self.fetchTargetName
		self.sourceFetcher.unpack(self.sourceBaseDir, self.sourceSubDir,
			self.sourceExportSubdir)

		port.setFlag('unpack', self.index)

	def validateChecksum(self, port):
		"""Make sure that the MD5-checksum matches the expectations"""

		if not self.sourceFetcher.sourceShouldBeValidated:
			return

		if not 'size' in self.checksums:
			warn('No CHECKSUM_SIZE key found in recipe for '
				 + self.fetchTargetName)
		if not 'md5' in self.checksums:
			warn('No CHECKSUM_MD5 key found in recipe for '
				 + self.fetchTargetName)
		if not 'rmd160' in self.checksums:
			warn('No CHECKSUM_RMD160 key found in recipe for '
				 + self.fetchTargetName)
		if not 'sha512' in self.checksums:
			warn('No CHECKSUM_SHA512 key found in recipe for '
				 + self.fetchTargetName)

		if not 'md5' in self.checksums and not 'rmd160' in self.checksums \
		and not 'sha512' in self.checksums:
			sysExit('No checksum found!')

		print 'Validating checksums of ' + self.fetchTargetName
		size = 0
		md5 = hashlib.md5()
		rmd160 = hashlib.new('ripemd160')
		sha512 = hashlib.sha512()

		f = open(self.fetchTarget, 'rb')
		while True:
			d = f.read(16384)

			if not d:
				break

			size += len(d)
			md5.update(d)
			rmd160.update(d)
			sha512.update(d)
		f.close()

		if 'size' in self.checksums and size != self.checksums['size']:
			sysExit('Expected size: ' + str(self.checksums['size']) + '\n'
					+ 'Found size: ' + str(size))
		if 'md5' in self.checksums and md5.hexdigest() != self.checksums['md5']:
			sysExit('Expected MD5: ' + self.checksums['md5'] + '\n'
					+ 'Found MD5: ' + md5.hexdigest())
		if 'rmd160' in self.checksums \
		and rmd160.hexdigest() != self.checksums['rmd160']:
			sysExit('Expected RIPEMD-160: ' + self.checksums['rmd160'] + '\n'
					+ 'Found RIPEMD-160: ' + rmd160.hexdigest())
		if 'sha512' in self.checksums \
		and sha512.hexdigest() != self.checksums['sha512']:
			sysExit('Expected SHA-512: ' + self.checksums['sha512'] + '\n'
					+ 'Found SHA-512: ' + sha512.hexdigest())

	def isFromSourcePackage(self):
		"""Determines whether or not this source comes from a source package"""

		return self.uris[0].lower().startswith('pkg:')

	def isFromRiggedSourcePackage(self):
		"""Determines whether or not this source comes from a source package
		   that has been rigged (i.e. does have the patches already applied)"""

		return (self.uris[0].lower().startswith('pkg:')
				and '_source_rigged-' in self.uris[0].lower())

	def patch(self, port):
		"""Apply any patches to this source"""

		# Check to see if the source has already been patched.
		if port.checkFlag('patchset', self.index) and not getOption('force'):
			print 'Skipping patchset for ' + self.fetchTargetName
			return True

		# use an implicit git repository for improved patch handling.
		ensureCommandIsAvailable('git')
		if not self._isInGitWorkingDirectory(self.sourceDir):
			# import sources into pristine git repository
			self._initImplicitGitRepo()
		elif self.patches:
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
					check_call(['git', 'am', '-3', patch], cwd=self.sourceDir,
							   env=self.gitEnv)
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
				  + self.fetchTargetName)
			return

		print('Committing changes done in patch function for '
			  + self.fetchTargetName)
		check_call(['git', 'commit', '-a', '-q', '-m', 'patch function'],
				   cwd=self.sourceDir, env=self.gitEnv)
		check_call(['git', 'tag', '-f', 'PATCH_FUNCTION', 'HEAD'],
				   cwd=self.sourceDir)

	def extractPatchset(self, patchSetFilePath, archPatchSetFilePath):
		"""Extract the current set of patches applied to git repository,
		   taking care to not include the programatic changes introduced
		   during the patch phase"""

		if not os.path.exists(self.sourceDir):
			sysExit("Can't extract patchset for " + self.sourceDir
					+ " as the source directory doesn't exist yet")

		print 'Extracting patchset for ' + self.fetchTargetName
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
						'PATCH_FUNCTION', 'haikuport'], cwd=self.sourceDir,
						env=self.gitEnv)

		patchSetDirectory = os.path.dirname(patchSetFilePath)
		if not os.path.exists(patchSetDirectory):
			os.mkdir(patchSetDirectory)
		with open(patchSetFilePath, 'w') as patchSetFile:
			check_call(['git', 'format-patch', '-kp', '--stdout', 'ORIGIN'],
					   stdout=patchSetFile, cwd=self.sourceDir, 
					   env=self.gitEnv)

		if needToRebase:
			# put PATCH_FUNCTION back in
			check_call(['git', 'rebase', '-q', 'PATCH_FUNCTION', 'haikuport'],
					   cwd=self.sourceDir, env=self.gitEnv)

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

	def exportSources(self, targetDir, rigged):
		"""Export sources into a folder"""

		if not os.path.exists(targetDir):
			os.makedirs(targetDir)
		if rigged:
			# export the sources in 'rigged' state, i.e. in directly usable
			# form, with patches already applied
			check_call('tar c --exclude=.git . | tar x -C %s' % targetDir,
					   cwd=self.sourceDir, shell=True)
		else:
			# unpack the archive into the targetDir
			if self.sourceSubDir:
				os.mkdir(targetDir + '/' + self.sourceSubDir)
			self.sourceFetcher.unpack(targetDir, self.sourceSubDir,
				self.sourceExportSubdir)
			if self.sourceSubDir:
				foldSubdirIntoSourceDir(self.sourceSubDir, targetDir)

	def exportAdditionalFiles(self, targetDir):
		"""Export any additional files into given folder"""

		if not self.additionalFiles:
			return

		if not os.path.exists(targetDir):
			os.makedirs(targetDir)
		for additionalFile in self.additionalFiles:
			command = ('tar -c "%s" | tar -x -C "%s"'
					   % (os.path.basename(additionalFile), targetDir))
			check_call(command, cwd=os.path.dirname(additionalFile), shell=True)

	def adjustToChroot(self, port):
		"""Adjust directories to chroot()-ed environment"""

		self.fetchTarget = None

		# adjust all relevant directories
		pathLengthToCut = len(port.workDir)
		self.sourceBaseDir = self.sourceBaseDir[pathLengthToCut:]
		self.sourceDir = self.sourceDir[pathLengthToCut:]
		self.additionalFiles = [
			additionalFile[pathLengthToCut:]
			for additionalFile in self.additionalFiles
		]

	def _initImplicitGitRepo(self):
		"""Import sources into git repository"""

		ensureCommandIsAvailable('git')
		check_call(['git', 'init'], cwd=self.sourceDir)
		check_call(['git', 'config', 'gc.auto', '0'], cwd=self.sourceDir)
			# Disable automatic garbage collection. This works around an issue
			# with git failing to do that with the haikuwebkit repository.
		check_call(['git', 'symbolic-ref', 'HEAD', 'refs/heads/haikuport'],
				   cwd=self.sourceDir)
		check_call(['git', 'add', '-f', '.'], cwd=self.sourceDir)
		check_call(['git', 'commit', '-m', 'import', '-q'],
				   cwd=self.sourceDir, env=self.gitEnv)
		check_call(['git', 'tag', 'ORIGIN'], cwd=self.sourceDir)

	def _isInGitWorkingDirectory(self, path):
		"""Returns whether the given source directory path is in a git working
		   directory. path must be under self.sourceBaseDir."""

		while (path == self.sourceBaseDir
				or path.startswith(self.sourceBaseDir + '/')):
			if os.path.exists(path + '/.git'):
				return True
			if path == self.sourceBaseDir:
				return False;
			path = path[0:path.rfind('/')]

		return False
