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
# Copyright 2020 François Revol
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .Configuration import Configuration
from .Utils import ensureCommandIsAvailable, info, sysExit, unpackArchive, warn

import json
import sys

try:
	import requests
except ImportError:
	pass

# -----------------------------------------------------------------------------

# -- Checks releases from GitHub --------------------------------------------------


class ReleaseCheckerForGitHub(object):

	def __init__(self, uri, version):
		self.uri = uri
		self.currentVersion = version

		#(unusedType, self.uri, self.rev) = parseCheckoutUri(uri)

	def check(self):
		parts = self.uri.split("/")
		if parts[2] != "github.com":
			sysExit('Bad URI in GitHub ReleaseChecker!')

		project = "/".join(parts[3:5])
		# some "releases" are actually just tags
		releases = "releases/download" in self.uri
		endpoint = "releases" if releases else "tags"

		request = "http://api.github.com/repos/%s/%s" % (project, endpoint)
		print("Checking from %s" % request)
		headers = {
		    "Accept": "application/vnd.github.v3+json",
		    "User-Agent": "HaikuPorter"
		}
		with requests.get(request, headers=headers) as r:
			j = r.json()
			if not j:
				print("Error getting JSON from %s" % request)
				return False
			if len(j) == 0:
				print("No release found from %s" % request)
				return False
			if releases:
				# first one should be latest
				tag_name = j[0]['tag_name']
				name = j[0]['name']
				if self.currentVersion != tag_name:
					return tag_name
				if self.currentVersion != name:
					return name

			else:  # tags
				if self.currentVersion not in parts[-1]:
					print("cannot find version prefix in URI")
					return False
				prefix = parts[-1][0:parts[-1].find(self.currentVersion)]
				# first one should be latest
				# actually not always, cf. cronie-crond/cronie
				name = j[0]['name']
				name = name[len(prefix):]
				if self.currentVersion != name:
					return name

		return False


# -- release checker factory function for given URI ----------------------------


def createReleaseChecker(uri, version):
	"""Creates an appropriate release checker for the given URI"""

	if "requests" not in sys.modules:
		sysExit('requests missing for ReleaseChecker!')

	lowerUri = uri.lower()
	if "://github.com/" in lowerUri:
		return ReleaseCheckerForGitHub(uri, version)
	else:
		return None
