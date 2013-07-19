# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.RecipeTypes import *
from HaikuPorter.ShellScriptlets import (configFileEvaluatorScript,
										 getShellVariableSetters)
from HaikuPorter.Utils import check_output, filteredEnvironment, sysExit, warn

from subprocess import CalledProcessError
import types


# -- /etc/haikuports.conf and *.recipe parser --------------------------------

class ConfigParser(object):
	def __init__(self, filename, attributes, shellVariables={}):
		self.entriesByExtension = {}
		self.definedPhases = []

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
			output = check_output(['/bin/bash', '-c', wrapperScript],
								  env=shellEnv)
		except (OSError, CalledProcessError):
			sysExit("Can't evaluate config file: " + filename)

		# ... and collect the resulting configurations (one per line)
		lines = output.splitlines()
		for line in lines:
			key, separator, valueString = line.partition('=')
			if not separator:
				sysExit('evaluating file %s produced illegal '
						'key-values line:\n  %s\nexpected "<key>=<value>"\n'
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
				if not baseKey in entries:
					entries[baseKey] = {}

			attrType = attributes[baseKey]['type']
			if attrType == types.StringType:
				if attributes[baseKey]['indexable']:
					entries[baseKey][index] = valueString
				else:
					entries[key] = valueString
			elif attrType == types.IntType:
				try:
					if attributes[baseKey]['indexable']:
						entries[baseKey][index] = int(valueString)
					else:
						entries[key] = int(valueString)
				except ValueError:
					sysExit('evaluating file %s produced illegal value '
							'"%s" for key %s, expected an <integer> value'
							% (filename, key, valueString))
			elif attrType == types.ListType:
				values = [v.strip() for v in valueString.splitlines()]
				values = [v for v in values if len(v) > 0]
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
				if valueString.upper() not in Phase.getAllowedValues():
					sysExit('evaluating file %s\nproduced illegal value "%s" '
							'for key %s\nexpected one of: %s'
							% (filename, key, valueString,
							   ','.join(Phase.getAllowedValues())))
				entries[key] = valueString.upper()
			elif attrType == MachineArchitecture:
				entries[key] = {}
				knownArchitectures = MachineArchitecture.getAll()
				valueString = valueString.lower()
				if valueString not in knownArchitectures:
					architectures = ','.join(knownArchitectures)
					sysExit('%s refers to unknown machine-architecture %s\n'
							'known machine-architectures: %s'
							% (filename, valueString, architectures))
				entries[key] = valueString
			elif attrType == Architectures:
				entries[key] = {}
				for value in [v.lower() for v in valueString.split()]:
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
				entries[key] = YesNo.toBool(self, valueString)
			else:
				sysExit('type of key %s in file %s is unsupported'
						% (key, filename))
		# for entries in self.entriesByExtension.values():
		#	for key in entries:
		#		print key + " = " + str(entries[key])

	def getEntriesForExtension(self, extension):
		if extension in self.entriesByExtension:
			return self.entriesByExtension[extension]
		else:
			return {}

	def getExtensions(self):
		return self.entriesByExtension.keys()

	def getDefinedPhases(self):
		return self.definedPhases

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
				component = component[1:-1]
			unquotedComponents.append(component)
		return unquotedComponents
