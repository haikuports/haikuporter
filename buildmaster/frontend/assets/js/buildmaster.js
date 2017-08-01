'use strict';


function findElement(elementSelector, baseElement)
{
	if (baseElement === undefined)
		baseElement = document;

	return baseElement.querySelector(elementSelector);
}


function removeElement(element)
{
	element.parentElement.removeChild(element);
}


function removeElements(selector, baseElement)
{
	if (baseElement === undefined)
		baseElement = document;

	var elements = baseElement.querySelectorAll(selector);
	for (var i = 0; i < elements.length; i++)
		removeElement(elements[i]);
}


function setElementContent(elementSelector, content, baseElement)
{
	findElement(elementSelector, baseElement).innerText = content;
}


function wrapElements(selector, elementType, attributes, baseElement)
{
	if (baseElement === undefined)
		baseElement = document;

	var nodeList = baseElement.querySelectorAll(selector);
	for (var i = 0; i < nodeList.length; i++) {
		var element = nodeList[i];
		var content = element.innerText;
		var wrapper = document.createElement(elementType);
		for (var propertyName in attributes) {
			if (!attributes.hasOwnProperty(propertyName))
				continue;

			wrapper.setAttribute(propertyName,
				attributes[propertyName].replace('%s', content));
		}

		element.parentElement.replaceChild(wrapper, element);
		wrapper.appendChild(element);
	}
}


function mapContentFromObject(object, map, baseElement)
{
	for (var propertyName in map) {
		if (!map.hasOwnProperty(propertyName))
			continue;

		var source = object;
		var parts = propertyName.split('.');
		for (var i = 0; i < parts.length; i++) {
			source = source[parts[i]];
			if (!(source instanceof Object))
				break;
		}

		setElementContent(map[propertyName], source, baseElement);
	}
}


function createFromTemplate(templateSelector, baseElement)
{
	var template = findElement(templateSelector, baseElement).cloneNode(true);
	template.attributes.removeNamedItem('id');
	template.classList.remove('template');
	return template;
}


function getSearchParameter(parameterName, expression, defaultValue)
{
	var regex = new RegExp('[?&]' + parameterName + '=('
		+ (expression !== undefined ? expression : '[^&]*') + ')');
	var match = regex.exec(window.location.search);
	if (match === null)
		return defaultValue;

	return match[1];
}


function BuildMaster()
{
	this.baseDir = 'buildruns/';
	var buildrunDir
		= getSearchParameter('buildrunDir', '[a-zA-Z0-9][a-zA-Z0-9.-/]*', '');
	if (buildrunDir.length > 0)
		buildrunDir += '/';

	this.buildrunDir = this.baseDir + buildrunDir;

	this.fetch(this.baseDir + 'buildruns.txt',
		this.populateBuildruns.bind(this));

	setElementContent('#loadStatus', 'Loading buildrun status...');
	this.fetch(this.buildrunDir + 'output/status.json', function(response) {
			this.status = JSON.parse(response);
			setElementContent('#loadStatus', '');
			this.showStatus();
		}.bind(this), function(status) {
			setElementContent('#loadStatus', 'Failed to load buildrun status: '
				+ status);
		});
}


BuildMaster.prototype.fetch = function(resource, successCallback, errorCallback)
{
	var request = new XMLHttpRequest();
	request.open('GET', resource);
	request.onreadystatechange = function() {
			if (request.readyState != 4)
				return;

			if (request.status == 200 && successCallback !== undefined)
				successCallback(request.responseText);
			else if (errorCallback !== undefined)
				errorCallback(request.status);
		};

	request.send(null);
}


BuildMaster.prototype.populateBuildruns = function(response)
{
	var parentElement = findElement('#buildrunSelector');
	response.split('\n').reverse().forEach(function(buildrunDir) {
			if (buildrunDir.length == 0)
				return;

			var element = document.createElement('option');
			element.value = buildrunDir;
			element.innerText = buildrunDir;
			if (this.baseDir + buildrunDir + '/' == this.buildrunDir)
				element.setAttribute('selected', 'selected');

			parentElement.appendChild(element);
		}.bind(this));

	parentElement.addEventListener('change', function(event) {
			window.location.replace(window.location.pathname + '?buildrunDir='
				+ event.target.value);
		});
}


BuildMaster.prototype.showStatus = function()
{
	mapContentFromObject(this.status, {
			'portsTreeHead': '#portsTreeHead',
			'buildStatus': '#buildStatus'
		});

	var addBuildCount = function(name, count, linkTarget) {
			var element = createFromTemplate('#buildCountTemplate');
			setElementContent('.name', name, element);
			setElementContent('.buildCount', count, element);
			findElement('.link', element).href = linkTarget;
			findElement('#buildCounts').appendChild(element);
		};

	var addBuilder = function(parentElement, builder) {
			var element = createFromTemplate('#builderTemplate');
			mapContentFromObject(builder, {
					'name': '.builderName',
					'currentBuild.number': '.currentBuild .buildNumber',
					'currentBuild.build.port.revisionedName':
						'.currentBuild .revisionedName',
				}, element);

			parentElement.appendChild(element);
		};

	var addBuilderList = function(targetSelector, builderList) {
			var parentElement = findElement(targetSelector);
			setElementContent('.count', builderList.length, parentElement);
			builderList.forEach(addBuilder.bind(undefined, parentElement));
			return builderList.length;
		};

	var totalBuilders = 0;
	totalBuilders += addBuilderList('#activeBuilders',
		this.status.builders.active);
	totalBuilders += addBuilderList('#reconnectingBuilders',
		this.status.builders.reconnecting);
	totalBuilders += addBuilderList('#lostBuilders',
		this.status.builders.lost);

	setElementContent('.count', totalBuilders, findElement('#builders'));

	var addString = function(parentElement, className, string) {
			var element = document.createElement('div');
			element.className = className;
			element.innerText = string;
			parentElement.appendChild(element);
		};

	var addStringList = function(targetElement, className, stringList) {
			setElementContent('.count', stringList.length,
				targetElement.parentElement);
			if (stringList.length > 0) {
				stringList.forEach(
					addString.bind(undefined, targetElement, className));
			} else
				removeElement(targetElement.parentElement);
		};

	var addBuild = function(parentElement, build) {
			var element = createFromTemplate('#scheduledBuildTemplate');
			mapContentFromObject(build, {
					'port.revisionedName': '.revisionedName'
				}, element);

			parentElement.appendChild(element);

			addStringList(findElement('.buildNumbers', element),
				'buildNumber', build.buildNumbers);
			addStringList(findElement('.resultingPackages', element),
				'packageName', build.resultingPackages);
			addStringList(findElement('.requiredPackages', element),
				'packageName', build.requiredPackages);
			addStringList(findElement('.missingPackages', element),
				'packageID', build.missingPackageIDs);
		};

	var addBuildList = function(name, targetSelector, buildList) {
			var parentElement = findElement(targetSelector);
			addBuildCount(name, buildList.length, targetSelector);
			setElementContent('.count', buildList.length, parentElement);
			buildList.forEach(addBuild.bind(undefined, parentElement));
			return buildList.length;
		};

	var totalBuilds = 0;
	totalBuilds += addBuildList('Active', '#activeBuilds',
		this.status.builds.active);
	totalBuilds += addBuildList('Scheduled', '#scheduledBuilds',
		this.status.builds.scheduled);
	totalBuilds += addBuildList('Blocked', '#blockedBuilds',
		this.status.builds.blocked);
	totalBuilds += addBuildList('Complete', '#completeBuilds',
		this.status.builds.complete);
	totalBuilds += addBuildList('Failed', '#failedBuilds',
		this.status.builds.failed);
	totalBuilds += addBuildList('Lost', '#lostBuilds',
		this.status.builds.lost);

	addBuildCount('Total', totalBuilds, '#builds');
	setElementContent('.count', totalBuilds, findElement('#builds'));

	wrapElements('#masterLog', 'a', {
			'href': this.buildrunDir + 'output/master.log',
			'target': '_blank'
		});
	wrapElements('.buildNumber', 'a', {
			'href': this.buildrunDir + 'output/builds/%s.log',
			'target': '_blank'
		});
	wrapElements('.builderName', 'a', {
			'href': this.buildrunDir + 'output/builders/%s.log',
			'target': '_blank'
		});
	wrapElements('#portsTreeHead', 'a', {
			'href': 'https://github.com/haikuports/haikuports/commit/%s',
			'target': '_blank'
		});

	removeElements('.template');

	if (typeof this.onstatusloaded === 'function')
		this.onstatusloaded();
}


function init()
{
	window.buildMaster = new BuildMaster();
	window.addEventListener('beforeunload', function() {
			localStorage.scrollOffset = window.pageYOffset;
		});

	if (localStorage.scrollOffset !== undefined) {
		window.buildMaster.onstatusloaded = function() {
				window.scrollTo(0, localStorage.scrollOffset);
			};
	}
}


window.addEventListener('load', init);
