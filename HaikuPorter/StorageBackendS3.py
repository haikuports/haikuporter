# -*- coding: utf-8 -*-
#
# Copyright 2024 Michael Lotz
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import boto3

from contextlib import contextmanager

# -- StorageBackendS3 class ---------------------------------------------------

class StorageBackendS3():
	def __init__(self, packagesPath, config):
		if 'endpoint_url' not in config:
			raise Exception('missing endpoint_url in s3 config')
		if 'region_name' not in config:
			raise Exception('region_name not in s3 config')
		if 'access_key_id' not in config:
			raise Exception('missing access_key_id in s3 config')
		if 'secret_access_key' not in config:
			raise Exception('missing secret_access_key in s3 config')
		if 'bucket_name' not in config:
			raise Exception('missing bucket_name in s3 config')

		self.bucketName = config['bucket_name']
		self.prefix = config.get('prefix', '')
		self.packagesPrefix = self.prefix + 'packages/'

		self.client = boto3.client('s3',
			endpoint_url=config['endpoint_url'],
			aws_access_key_id=config['access_key_id'],
			aws_secret_access_key=config['secret_access_key'],
			region_name=config['region_name'])

	def readPackage(self, packageName, file):
		self.client.download_fileobj(self.bucketName,
			f'{self.packagesPrefix}{packageName}', file)

	def writePackage(self, packageName, file):
		self.client.upload_fileobj(file, self.bucketName,
			f'{self.packagesPrefix}{packageName}')

	def writeFile(self, fileName, file):
		self.client.upload_fileobj(file, self.bucketName,
			f'{self.prefix}{fileName}')

	def listPackages(self):
		kwargs = {
			'Bucket': self.bucketName,
			'Prefix': self.packagesPrefix
		}

		result = []
		while True:
			response = self.client.list_objects_v2(**kwargs)
			contents = response['Contents']
			for item in contents:
				result.append(item['Key'].removeprefix(self.packagesPrefix))

			if not response.get('IsTruncated', False):
				break

			kwargs['StartAfter'] = contents[-1]['Key']

		return result

	def deletePackage(self, packageName):
		self.client.delete_object(Bucket=self.bucketName,
			Key=f'{self.packagesPrefix}{packageName}')
