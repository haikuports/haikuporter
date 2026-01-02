# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import functools
from subprocess import CalledProcessError, check_output

from .RecipeTypes import (Architectures, Extendable, LinesOfText,
                          MachineArchitecture, Phase, ProvidesList,
                          RequiresList, Status, YesNo)
from .ShellScriptlets import configFileEvaluatorScript, getShellVariableSetters
from .Utils import filteredEnvironment, sysExit, warn

# -- haikuports.conf and *.recipe parser --------------------------------

class ConfigParser(object):
	def __init__(self, filename, attributes, shellVariables):

		## REFACTOR environment setup and conf location into a single function
		## that then calls the ConfigParser and either passes in the file path
		## or the contents of the file

		# set up the shell environment -- we want it to inherit some of our
		# variables
		shellEnv = filteredEnvironment()
		shellEnv['recipePhases'] = ' '.join(Phase.getAllowedValues())

		# execute the config file via the shell ....
		supportedKeysString = '|'.join(attributes.keys())
		shellVariables = shellVariables.copy()
		shellVariables['supportedKeysPattern'] = supportedKeysString
		shellVariables['fileToParse'] = filename

		wrapperScript = (getShellVariableSetters(shellVariables)
						 + configFileEvaluatorScript)
		try:
			output = check_output(['bash', '-c', wrapperScript], env=shellEnv).decode('utf-8')
		except (OSError, CalledProcessError):
			sysExit("Can't evaluate config file: " + filename)

		# ... and collect the resulting configurations (one per line)

		self.entriesByExtension = {}
		self.definedPhases = []

		lines = output.splitlines()
		for line in lines:
			## REFACTOR into a testable method that can parse a single line
			key, separator, valueString = line.partition('=')
			if not separator:
				sysExit('evaluating file %s produced illegal '
						'key-values line:\n	 %s\nexpected "<key>=<value>"\n'
						'output of configuration script was: %s\n'
						% (filename, line, output))

			# some keys may have a package-specific extension, check:
			if key in attributes:
				# unextended key
				baseKey = key
				extension = ''
				index = '1'
			else:
				baseKey = ''
				subKeys = key.split('_')
				while subKeys:
					subKey = subKeys.pop(0)
					baseKey += ('_' if baseKey else '') + subKey
					if baseKey in attributes:
						if attributes[baseKey]['extendable'] != Extendable.NO:
							extension = '_'.join(subKeys)
							break
						if attributes[baseKey]['indexable']:
							index = None
							if len(subKeys) == 0:
								index = '1'
								break
							if len(subKeys) == 1 and subKeys[0].isdigit():
								index = subKeys[0]
								break
						warn('Ignoring key %s in file %s' % (key, filename))
						continue
				else:
					# might be a <PHASE>_DEFINED
					isPhaseKey = False
					if key.endswith('_DEFINED'):
						phase = key[:-8]
						if phase in Phase.getAllowedValues():
							isPhaseKey = True
							self.definedPhases.append(phase)

					if not isPhaseKey:
						# skip unsupported key, just in case
						warn('Key %s in file %s is unsupported, ignoring it'
							 % (key, filename))
					continue

			# create empty dictionary for new extension
			if extension not in self.entriesByExtension:
				self.entriesByExtension[extension] = {}

			entries = self.entriesByExtension[extension]

			valueString = valueString.replace(r'\n', '\n')
			# replace quoted newlines by real newlines

			if attributes[baseKey]['indexable']:
				if baseKey not in entries:
					entries[baseKey] = {}

			## REFACTOR into one method per if/elif branch
			attrType = attributes[baseKey]['type']
			if attrType == bytes:
				if attributes[baseKey]['indexable']:
					entries[baseKey][index] = valueString
				else:
					entries[key] = valueString
			elif attrType == int:
				try:
					if attributes[baseKey]['indexable']:
						entries[baseKey][index] = int(valueString)
					else:
						entries[key] = int(valueString)
				except ValueError:
					sysExit('evaluating file %s produced illegal value '
							'"%s" for key %s, expected an <integer> value'
							% (filename, valueString, key))
			elif attrType in [list, ProvidesList, RequiresList]:
				values = [v.strip() for v in valueString.splitlines()]
				values = [v for v in values if len(v) > 0]
				# explicitly protect against '-' in names of provides or
				# requires declarations
				if attrType in [ProvidesList, RequiresList]:
					values = [v.lower() for v in values]
					for value in values:
						if '-' in value.split()[0]:
							sysExit('evaluating file %s produced illegal value '
									'"%s" for key %s\n'
									'dashes are not allowed in provides- or '
									'requires declarations'
									% (filename, value, key))
				if attributes[baseKey]['indexable']:
					entries[baseKey][index] = values
				else:
					entries[key] = values
			elif attrType == LinesOfText:
				# like a list, but only strip empty lines in front of and
				# after the text
				values = [v.strip() for v in valueString.splitlines()]
				while values and len(values[0]) == 0:
					values.pop(0)
				while values and len(values[-1]) == 0:
					values.pop()
				entries[key] = values
			elif attrType == Phase:
				#valueString = valueString.upper()
				if valueString not in Phase.getAllowedValues():
					sysExit('evaluating file %s\nproduced illegal value "%s" '
							'for key %s\nexpected one of: %s'
							% (filename, valueString, key,
							   ','.join(Phase.getAllowedValues())))
				entries[key] = valueString
			elif attrType == MachineArchitecture:
				entries[key] = {}
				knownArchitectures = MachineArchitecture.getAll()
				#valueString = valueString.lower()
				if valueString not in knownArchitectures:
					architectures = ','.join(knownArchitectures)
					sysExit('%s refers to unknown machine-architecture %s\n'
							'known machine-architectures: %s'
							% (filename, valueString, architectures))
				entries[key] = valueString
			elif attrType == Architectures:
				entries[key] = {}
				for value in valueString.split():
					architecture = ''
					if value.startswith('?'):
						status = Status.UNTESTED
						architecture = value[1:]
					elif value.startswith('!'):
						status = Status.BROKEN
						architecture = value[1:]
					else:
						status = Status.STABLE
						architecture = value
					knownArchitectures = Architectures.getAll()
					if architecture == 'ALL':
						if len(entries[key]) > 0:
							sysExit("%s specifies 'ALL' after other architectures"
									% (filename))
						for machineArch in MachineArchitecture.getAll():
							entries[key][machineArch] = status
					else:
						#architecture = architecture.lower()
						if architecture not in knownArchitectures:
							architectures = ','.join(knownArchitectures)
							sysExit('%s refers to unknown architecture %s\n'
									'known architectures: %s'
									% (filename, architecture, architectures))
						entries[key][architecture] = status
				if 'any' in entries[key] and len(entries[key]) > 1:
					sysExit("%s specifies both 'any' and other architectures"
							% (filename))
				if 'source' in entries[key] and len(entries[key]) > 1:
					sysExit("%s specifies both 'source' and other architectures"
							% (filename))
			elif attrType == YesNo:
				valueString = valueString.lower()
				if valueString not in YesNo.getAllowedValues():
					sysExit("Value for %s should be 'yes' or 'no' in %s"
							% (key, filename))
				entries[key] = YesNo.toBool(valueString)
			else:
				sysExit('type of key %s in file %s is unsupported'
						% (key, filename))
				# for entries in self.entriesByExtension.values():
				# for key in entries:
				#		print key + " = " + str(entries[key])

	def getEntriesForExtension(self, extension):
		if extension in self.entriesByExtension:
			return self.entriesByExtension[extension]
		else:
			return {}

	@property
	def extensions(self):
		return self.entriesByExtension.keys()


	## REFACTOR - consider using simple functions for this
	@staticmethod
	def splitItem(string):
		components = []
		if not string:
			return components

		component = ''
		inQuote = False
		for c in string:
			if inQuote:
				component += c
				if c == '"':
					inQuote = False
				continue

			if c.isspace():
				if component:
					components.append(component)
					component = ''
				continue

			component += c
			if c == '"':
				inQuote = True

		if component:
			components.append(component)
			component = ''

		return components

	@staticmethod
	def splitItemAndUnquote(string):
		components = ConfigParser.splitItem(string)
		unquotedComponents = []
		for component in components:
			if component and component[0] == '"' and component[-1] == '"':
					# use a regex if this called a lot
				component = component[1:-1]
			unquotedComponents.append(component)
		return unquotedComponents

	@staticmethod
	def configurationStringFromDict(config):
		configurationString = ''
		for key in config.keys():
			configurationString += key + '="'

			if isinstance(config[key], list):
				configurationString += functools.reduce(
					lambda result, item: result + ' ' + item, config[key],
					'').strip()
			elif type(config[key]) is bool:
				configurationString += 'yes' if config[key] else 'no'
			else:
				configurationString += str(config[key])

			configurationString += '"\n'

		return configurationString
