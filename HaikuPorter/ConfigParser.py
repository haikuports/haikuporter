# -*- coding: utf-8 -*-
# copyright 2013 Oliver Tappe

# -- Modules ------------------------------------------------------------------

from HaikuPorter.RecipeTypes import *
from HaikuPorter.ShellScriptlets import configFileEvaluatorScript
from HaikuPorter.Utils import check_output, sysExit, warn

import os
from subprocess import CalledProcessError
import types


# -- /etc/haikuports.conf and *.recipe parser --------------------------------

class ConfigParser:
	def __init__(self, filename, attributes, shellVariables={}):
		self.entries = {}

		# set up the shell environment -- we want it to inherit some of our
		# variables
		shellEnv = os.environ
		shellEnv.update(shellVariables)

		# execute the config file via the shell ....
		supportedKeysString = '|'.join(attributes.keys())
		wrapperScript = configFileEvaluatorScript % (filename, 
													 supportedKeysString)
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

			# some keys may have package-specific extension, check:
			if key in attributes:
				baseKey = key
			else:
				baseKey = ''
				for subKey in key.split('_'):
					baseKey += ('_' if baseKey else '') + subKey
					if baseKey in attributes:
						break;
				else:
					# skip unsupported key, just in case
					warn('Key %s in file %s is unsupported, ignoring it'
						 % (key, filename))
					continue
			
			valueString = valueString.replace(r'\n', '\n')
				# replace quoted newlines by real newlines
				
			type = attributes[baseKey]['type']
			if type == types.StringType:
				self.entries[key] = valueString
			elif type == types.IntType:
				try:
					self.entries[key] = int(valueString)
				except ValueError:
					sysExit('evaluating file %s produced illegal value '
							'"%s" for key %s, expected an <integer> value'
							% (filename, key, valueString))
			elif type == types.ListType:
				values = [v.strip() for v in valueString.splitlines()]
				self.entries[key] = [v for v in values if len(v) > 0]
			elif type == LinesOfText:
				# like a list, but only strip empty lines in front of and
				# after the text
				values = [v.strip() for v in valueString.splitlines()]
				while values and len(values[0]) == 0:
					values.pop(0)
				while values and len(values[-1]) == 0:
					values.pop()
				self.entries[key] = values
			elif type == PhaseType:
				if valueString.upper() not in PhaseType.getAllowedValues():
					sysExit('evaluating file %s\nproduced illegal value "%s" '
							'for key %s\nexpected one of: %s'
							% (filename, key, valueString, 
							   ','.join(PhaseType.getAllowedValues())))
				self.entries[key] = valueString.upper()
			elif type == ArchitecturesType:
				self.entries[key] = {}
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
					knownArchitectures = ArchitecturesType.getArchitectures()
					if architecture not in knownArchitectures:
						architectures = ','.join(knownArchitectures)
						sysExit('%s refers to unknown architecture %s\n'
								'known architectures: %s'
								% (filename, architecture, architectures))
					self.entries[key][architecture] = status
				if 'any' in self.entries[key] and len(self.entries[key]) > 1:
					sysExit("%s specifies both 'any' and other architectures" 
							% (filename))
			else:
				sysExit('type of key %s in file %s is unsupported'
						% (key, filename))
		# for key in self.entries:
		#	print key + " = " + str(self.entries[key])

	def getEntries(self):
		return self.entries
