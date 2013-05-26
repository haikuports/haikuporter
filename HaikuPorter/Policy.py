# -*- coding: utf-8 -*-
# copyright 2013 Ingo Weinhold

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Utils import (sysExit)

import os
import re

allowedTopLevelEntries = [
	'.PackageInfo',
	'add-ons',
	'apps',
	'bin',
	'boot',
	'data',
	'develop',
	'documentation',
	'lib',
	'preferences',
	'settings'
]

# -- Policy checker class -----------------------------------------------------

class Policy(object):
	def __init__(self, strict):
		self.strict = strict

	def setPort(self, port):
		self.port = port

	def checkPackage(self, package, packageFile):
		self.package = package
		self.packageFile = packageFile

		self._checkTopLevelEntries()
		self._checkProvides()
		self._checkLibraryDependencies()

	def _checkTopLevelEntries(self):
		for entry in os.listdir('.'):
			if entry not in allowedTopLevelEntries:
				_severeViolation('Invalid top-level package entry "%s"' % entry)

	def _checkProvides(self):
		# get the list of provides names (without version)
		provides = set()
		for item in self.package.getRecipeKeys()['PROVIDES']:
			match = re.match('[^-/=!<>\s]+', item)
			if match:
				provides.add(match.group(0))

		# everything in bin/ must be declared as cmd:*
		for entry in os.listdir('bin'):
			name = 'cmd:' + entry
			if not self._hasProvidesEntry(provides, name):
				self._violation('no matching provides "%s" for "%s"'
					% (name, 'bin/' + entry))

		# library entries in lib/ must be declared as lib:*
		if os.path.exists('lib'):
			for entry in os.listdir('lib'):
				suffixIndex = entry.find('.so')
				if suffixIndex < 0:
					continue

				name = 'lib:' + entry[:suffixIndex]
				if not self._hasProvidesEntry(provides, name):
					self._violation('no matching provides "%s" for "%s"'
						% (name, 'lib/' + entry))

	def _hasProvidesEntry(self, provides, name):
		# make name a valid provides name by replacing '-' with '_'
		name = name.replace('-', '_')
		return name in provides

	def _checkLibraryDependencies(self):
		# TODO:...
		pass

	def _violation(self, message):
		if self.strict:
			self._severeViolation(message)
		else:
			print 'POLICY WARNING: ' + message

	def _severeViolation(self, message):
		sysExit('POLICY ERROR: ' + message)
