# -*- coding: utf-8 -*-
#
# Copyright 2007-2011 Brecht Machiels
# Copyright 2009-2010 Chris Roberts
# Copyright 2009-2011 Scott McCreary
# Copyright 2009 Alexander Deynichenko
# Copyright 2009 HaikuBot (aka RISC)
# Copyright 2010-2011 Jack Laxson (Jrabbit)
# Copyright 2011 Ingo Weinhold
# Copyright 2013-2014 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import os
import shutil
from subprocess import CalledProcessError, check_call, check_output

from .Configuration import Configuration
from .Options import getOption
from .SourceFetcher import (createSourceFetcher, foldSubdirIntoSourceDir,
                            parseCheckoutUri)
from .Utils import (ensureCommandIsAvailable, info, readStringFromFile,
                    storeStringInFile, sysExit, warn)

# -- A source archive (or checkout) -------------------------------------------

class Source(object):
	def __init__(self, port, index, uris, fetchTargetName, checksum,
				 sourceDir, patches, additionalFiles):
		self.index = index
		self.uris = uris
		self.fetchTargetName = fetchTargetName
		self.checksum = checksum
		self.patches = patches
		self.additionalFiles = additionalFiles

		## REFACTOR use property setters to handle branching based on instance
		## variables

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
				port.patchesDir + '/'
				+ patch for patch in self.patches if not patch.strip(' \t').startswith('#')
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
			recipeDirName = os.path.basename(port.baseDir)
			self.uris.append(downloadMirror + '/' + recipeDirName + '/'
							 + uriFileName + uriExtension)

		self.sourceFetcher = None
		self.fetchTarget = port.downloadDir + '/' + self.fetchTargetName
		self.fetchTargetIsArchive = True

		self.gitEnv = {
			'GIT_COMMITTER_EMAIL': Configuration.getPackagerEmail(),
			'GIT_COMMITTER_NAME': Configuration.getPackagerName().encode("utf-8"),
			'GIT_AUTHOR_EMAIL': Configuration.getPackagerEmail(),
			'GIT_AUTHOR_NAME': Configuration.getPackagerName().encode("utf-8"),
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
							info('Skipping download of source for '
								   + self.fetchTargetName)
						break
				else:
					warn("Stored SOURCE_URI is no longer in recipe, automatic "
						 u"repository update won't work")
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
				info('\nDownloading: ' + uri + ' ...')
				sourceFetcher = createSourceFetcher(uri, self.fetchTarget)
				sourceFetcher.fetch()

				# ok, fetching the source was successful, we keep the source
				# fetcher and store the URI that the source came from for
				# later runs
				self.sourceFetcher = sourceFetcher
				storeStringInFile(uri, self.fetchTarget + '.uri')
				return
			except Exception as e:
				if isinstance(e, CalledProcessError):
					info(e.output)
				if uri != self.uris[-1]:
					warn(('Unable to fetch source from %s (error: %s), '
						  + 'trying next location.') % (uri, e))
				else:
					warn(('Unable to fetch source from %s (error: %s)')
						 % (uri, e))

		# failed to fetch source
		sysExit('Failed to fetch source from all known locations.')

	def clean(self):
		if os.path.exists(self.fetchTarget):
			print('Removing source %s ...' % self.fetchTarget)
			if os.path.isdir(self.fetchTarget):
				shutil.rmtree(self.fetchTarget)
			else:
				os.remove(self.fetchTarget)

		uriFile = self.fetchTarget + '.uri'
		if os.path.exists(uriFile):
			os.remove(uriFile)

	def unpack(self, port):
		"""Unpack the source into the source directory"""

		# Check to see if the source was already unpacked.
		if port.checkFlag('unpack', self.index) and not getOption('force'):
			if not os.path.exists(self.sourceBaseDir):
				warn('Source dir has changed or been removed, unpacking in new dir')
				port.unsetFlag('unpack', self.index)
			else:
				info('Skipping unpack of ' + self.fetchTargetName)
				return

		# re-create source directory
		if os.path.exists(self.sourceBaseDir):
			info('Cleaning source dir for ' + self.fetchTargetName)
			shutil.rmtree(self.sourceBaseDir)
		os.makedirs(self.sourceBaseDir)

		info('Unpacking source of ' + self.fetchTargetName)
		self.sourceFetcher.unpack(self.sourceBaseDir, self.sourceSubDir,
			self.sourceExportSubdir)

		if not os.path.exists(self.sourceDir):
			sysExit(self.sourceSubDir + ' doesn\'t exist in sources! Define SOURCE_DIR in recipe?')

		port.setFlag('unpack', self.index)

	def populateAdditionalFiles(self, baseDir):
		if not self.additionalFiles:
			return

		additionalFilesDir = os.path.join(baseDir, 'additional-files')
		if self.index != '1':
			additionalFilesDir += '-' + self.index

		if not os.path.exists(additionalFilesDir):
			os.mkdir(additionalFilesDir)

		for additionalFile in self.additionalFiles:
			if os.path.isdir(additionalFile):
				shutil.copytree(additionalFile,
					os.path.join(additionalFilesDir,
						os.path.basename(additionalFile)))
			else:
				shutil.copy(additionalFile, additionalFilesDir)

	def validateChecksum(self, port):
		"""Make sure that the SHA256-checksum matches the expectations"""

		if not self.sourceFetcher.sourceShouldBeValidated:
			return

		# Check to see if the source was already unpacked.
		if port.checkFlag('validate', self.index) and not getOption('force'):
			info('Skipping checksum validation of ' + self.fetchTargetName)
			return

		info('Validating checksum of ' + self.fetchTargetName)
		hexdigest = calcChecksum = self.sourceFetcher.calcChecksum()

		if self.checksum is not None:
			if hexdigest != self.checksum:
				sysExit('Expected SHA-256: ' + self.checksum + '\n'
						+ 'Found SHA-256:	 ' + hexdigest)
		else:
			warn('----- CHECKSUM TEMPLATE -----')
			warn('CHECKSUM_SHA256%(index)s="%(digest)s"' % {
				"digest": hexdigest,
				"index": ("_" + self.index) if self.index != "1" else ""})
			warn('-----------------------------')

		if self.checksum is None:
			if not Configuration.shallAllowUnsafeSources():
				sysExit('No checksum found in recipe!')
			else:
				warn('No checksum found in recipe!')

		port.setFlag('validate', self.index)

	@property
	def isFromSourcePackage(self):
		"""Determines whether or not this source comes from a source package"""

		return self.uris[0].lower().startswith('pkg:')

	@property
	def isFromRiggedSourcePackage(self):
		"""Determines whether or not this source comes from a source package
		   that has been rigged (i.e. does have the patches already applied)"""

		return (self.uris[0].lower().startswith('pkg:')
				and '_source_rigged-' in self.uris[0].lower())

	def referencesFiles(self, files):
		if self.patches:
			for patch in self.patches:
				if patch in files:
					return True

		if self.additionalFiles:
			for additionalFile in self.additionalFiles:
				if os.path.isdir(additionalFile):
					# ensure there is a path separator at the end
					additionalFile = os.path.join(additionalFile, '')
					for fileName in files:
						if os.path.commonprefix([additionalFile, fileName]) \
								== additionalFile:
							return True
				elif additionalFile in files:
					return True

		return False

	def patch(self, port):
		"""Apply any patches to this source"""

		# Check to see if the source has already been patched.
		if port.checkFlag('patchset', self.index) and not getOption('force'):
			info('Skipping patchset for ' + self.fetchTargetName)
			return True

		if not getOption('noGitRepo'):
			# use an implicit git repository for improved patch handling.
			ensureCommandIsAvailable('git')
			if not self._isInGitWorkingDirectory(self.sourceDir):
				# import sources into pristine git repository
				self._initImplicitGitRepo()
			elif self.patches:
				# reset existing git repsitory before appling patchset(s) again
				self.reset()
		else:
			# make sure the patches can still be applied if no git repo
			ensureCommandIsAvailable('patch')

		patched = False
		try:
			# Apply patches
			for patch in self.patches:
				if not os.path.exists(patch):
					sysExit('patch file "' + patch + '" not found.')

				if getOption('noGitRepo'):
					info('Applying patch(set) "%s" ...' % patch)
					output = check_output(['patch', '--ignore-whitespace', '-p1', '-i',
								patch], cwd=self.sourceDir).decode('utf-8')
					info(output)
				else:
					if patch.endswith('.patchset'):
						info('Applying patchset "%s" ...' % patch)
						output = check_output(['git', 'am', '--ignore-whitespace', '-3',
									'--keep-cr', patch], cwd=self.sourceDir,
								   env=self.gitEnv).decode('utf-8')
						info(output)
					else:
						info('Applying patch "%s" ...' % patch)
						output = check_output(['git', 'apply', '--ignore-whitespace',
									'-p1', '--index', patch],
									cwd=self.sourceDir).decode('utf-8')
						info(output)
						output = check_output(['git', 'commit', '-q', '-m',
									'applying patch %s'
									% os.path.basename(patch)],
								   cwd=self.sourceDir, env=self.gitEnv).decode('utf-8')
						info(output)
				patched = True
		except:
			# Don't leave behind half-patched sources.
			if patched and not getOption('noGitRepo'):
				self.reset()
			raise

		if patched:
			port.setFlag('patchset', self.index)

		return patched

	def reset(self):
		"""Reset source to original state"""

		output = check_output(['git', 'reset', '--hard', 'ORIGIN'], cwd=self.sourceDir).decode('utf-8')
		info(output)
		output = check_output(['git', 'clean', '-f', '-d'], cwd=self.sourceDir).decode('utf-8')
		info(output)

	def commitPatchPhase(self):
		"""Commit changes done in patch phase."""

		# see if there are any changes at all
		changes = check_output(['git', 'status', '--porcelain'],
							   cwd=self.sourceDir).decode('utf-8')
		if not changes:
			info("Patch function hasn't changed anything for "
				  + self.fetchTargetName)
			return

		info('Committing changes done in patch function for '
			  + self.fetchTargetName)
		output = check_output(['git', 'commit', '-a', '-q', '-m', 'patch function'],
				   cwd=self.sourceDir, env=self.gitEnv).decode('utf-8')
		info(output)
		output = check_output(['git', 'tag', '--no-sign', '-f', 'PATCH_FUNCTION', 'HEAD'],
				   cwd=self.sourceDir).decode('utf-8')
		info(output)

	def extractPatchset(self, patchSetFilePath, archPatchSetFilePath):
		"""Extract the current set of patches applied to git repository,
		   taking care to not include the programatic changes introduced
		   during the patch phase"""

		if not os.path.exists(self.sourceDir):
			sysExit("Can't extract patchset for " + self.sourceDir
					+ u" as the source directory doesn't exist yet")

		if not os.path.exists(self.sourceDir + '/.git'):
			sysExit("Can't extract patchset as there is no .git repo for the the source directory "
					+ self.sourceDir)

		print('Extracting patchset for ' + self.fetchTargetName + " to " + patchSetFilePath)
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
			check_call(['git', '-c', 'core.abbrev=auto', 'format-patch', '-kp',
					   '--stdout', 'ORIGIN'], stdout=patchSetFile,
					   cwd=self.sourceDir, env=self.gitEnv)

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
		info(check_output(['git', 'init', '-b', 'main'], cwd=self.sourceDir).decode('utf-8'))
		info(check_output(['git', 'config', 'gc.auto', '0'], cwd=self.sourceDir).decode('utf-8'))
			# Disable automatic garbage collection. This works around an issue
			# with git failing to do that with the haikuwebkit repository.
		info(check_output(['git', 'symbolic-ref', 'HEAD', 'refs/heads/haikuport'],
				   cwd=self.sourceDir).decode('utf-8'))
		info(check_output(['git', 'add', '-f', '.'], cwd=self.sourceDir).decode('utf-8'))
		info(check_output(['git', 'commit', '-m', 'import', '-q'],
				   cwd=self.sourceDir, env=self.gitEnv).decode('utf-8'))
		info(check_output(['git', 'tag', '--no-sign', 'ORIGIN'],
				   cwd=self.sourceDir).decode('utf-8'))

	def _isInGitWorkingDirectory(self, path):
		"""Returns whether the given source directory path is in a git working
		   directory. path must be under self.sourceBaseDir."""

		while (path == self.sourceBaseDir
				or path.startswith(self.sourceBaseDir + '/')):
			if os.path.exists(path + '/.git'):
				return True
			if path == self.sourceBaseDir:
				return False
			path = path[0:path.rfind('/')]

		return False
