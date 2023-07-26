# -*- coding: utf-8 -*-
#
# Copyright 2021, Haiku, Inc. All rights reserved.
# Distributed under the terms of the MIT License.
#
# Authors:
#   Alexander von Gluck IV <kallisti5@unixzen.com>
from .Utils import warn, info

try:
	from pymongo import MongoClient
except ImportError:
	MongoClient = None


class ReporterMongo(object):

	def __init__(self, uri, branch, architecture):
		self.uri = uri
		self.branch = branch
		self.architecture = architecture
		if MongoClient:
			self.client = MongoClient(uri)
		else:
			self.client = None

	def connected(self):
		if self.client == None:
			warn('pymongo unavailable')
			return False
		try:
			self.client.server_info()
		except pymongo.errors.ServerSelectionTimeoutError as err:
			warn('unable to connect to MongoDB @ ' + self.uri)
			return False
		info('connected to MongoDB @ ' + self.uri + ' for reporting')
		return True

	def updateBuildrun(self, buildNumber, status):
		db = self.client[self.branch + '-' + self.architecture]
		buildrunCollection = db.buildruns
		mdbStatus = status.copy()
		mdbStatus["_id"] = buildNumber
		buildrunCollection.update_one({'_id': buildNumber}, {"$set": mdbStatus},
		                              upsert=True)
		self._updateBuilders(status)
		return

	def _updateBuilders(self, status):
		db = self.client[self.branch + '-' + self.architecture]
		builderCollection = db.builders
		for state in status["builders"].keys():
			for builder in status["builders"][state]:
				bldStatus = builder.copy()
				bldStatus["_id"] = builder["name"]
				bldStatus["status"] = state
				builderCollection.update_one({'_id': builder["name"]},
				                             {"$set": bldStatus},
				                             upsert=True)
