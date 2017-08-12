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
	findElement(elementSelector, baseElement).textContent = content;
}


function wrapElements(selector, elementType, attributes, contentSource, onclick,
	baseElement)
{
	if (baseElement === undefined)
		baseElement = document;

	var nodeList = baseElement.querySelectorAll(selector);
	for (var i = 0; i < nodeList.length; i++) {
		var element = nodeList[i];
		var content = contentSource
			? element.dataset[contentSource] : element.textContent;
		var wrapper = document.createElement(elementType);
		for (var propertyName in attributes) {
			if (!attributes.hasOwnProperty(propertyName))
				continue;

			wrapper.setAttribute(propertyName,
				attributes[propertyName].replace('%s', content));
		}

		element.parentElement.replaceChild(wrapper, element);
		wrapper.appendChild(element);
		wrapper.onclick = onclick;
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


function createInlineViewer(event)
{
	var target = event.currentTarget;
	var viewer = document.createElement('iframe');
	viewer.className = 'inlineLogViewer';
	viewer.src = target.dataset.url;

	target.onclick = () => {
			if (viewer.classList.contains('hidden'))
				viewer.classList.remove('hidden');
			else
				viewer.classList.add('hidden');
		};

	var container = target;
	while (!container.parentElement.classList.contains('logContainer'))
		container = container.parentElement;

	container.parentElement.insertBefore(viewer, container.nextSibling);
}


function BuildMaster()
{
	this.baseDir = 'buildruns/';
	var buildrunDir
		= getSearchParameter('buildrunDir', '[a-zA-Z0-9][a-zA-Z0-9.-/]*', '');
	if (buildrunDir.length > 0)
		this.fetchStatus(buildrunDir);
	else {
		this.fetch(this.baseDir + 'last_buildrun', function(response) {
				this.fetchStatus(response.replace('\n', ''));
			}.bind(this));
	}

	var viewToggle = document.querySelector('#viewToggle');
	viewToggle.onclick = this.toggleViewMode.bind(this);
	var viewMode = getSearchParameter('viewMode');
	if (viewMode && viewMode != this.viewMode())
		this.toggleViewMode({ target: viewToggle });
}


BuildMaster.prototype.fetchStatus = function(buildrunDir)
{
	this.buildrunDir = this.baseDir + buildrunDir + '/';

	this.fetch(this.baseDir + 'buildruns.txt',
		this.populateBuildruns.bind(this));

	setElementContent('#loadStatus', 'Loading buildrun status...');
	this.fetch(this.buildrunDir + 'output/status.json', function(response) {
			this.status = JSON.parse(response);
			setElementContent('#loadStatus', '');
			this.portsTreeOriginURL = this.status.portsTreeOriginURL;
			this.portsTreeHead = this.status.portsTreeHead;
			this.showStatus();
		}.bind(this), function(status) {
			setElementContent('#loadStatus', 'Failed to load buildrun status: '
				+ status);
		});
}


BuildMaster.prototype.toggleViewMode = function(event)
{
	if (document.documentElement.classList.toggle('compact'))
		event.target.textContent = 'Expanded';
	else
		event.target.textContent = 'Compact';
}


BuildMaster.prototype.viewMode = function()
{
	return document.documentElement.classList.contains('compact')
		? 'compact' : 'expanded';
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
			element.textContent = buildrunDir;
			if (this.baseDir + buildrunDir + '/' == this.buildrunDir)
				element.setAttribute('selected', 'selected');

			parentElement.appendChild(element);
		}.bind(this));

	parentElement.addEventListener('change', function(event) {
			window.location.replace(window.location.pathname + '?buildrunDir='
				+ event.target.value + '&viewMode=' + this.viewMode());
		}.bind(this));
}


BuildMaster.prototype.commitURL = function()
{
	return this.portsTreeOriginURL + '/commit/%s';
}


BuildMaster.prototype.recipeFileURL = function()
{
	return this.portsTreeOriginURL + '/blob/' + this.portsTreeHead + '/%s';
}


BuildMaster.prototype.rawLogURL = function(path)
{
	return this.buildrunDir + 'output/' + path;
}


BuildMaster.prototype.logViewerURL = function(path)
{
	return 'logviewer.html?' + this.rawLogURL(path);
}


BuildMaster.prototype.addLogs = function(selector, path)
{
	Array.from(document.querySelectorAll(selector)).forEach((element) => {
			var source = element.textContent;
			if (!source)
				return;

			var logs = createFromTemplate('#logTemplate');
			Array.from(logs.querySelectorAll('.log')).forEach(
				(log) => log.setAttribute('data-source', source));
			element.appendChild(logs);
		});

	wrapElements(selector + ' .raw', 'a', {
			'href': this.rawLogURL(path),
			'target': '_blank',
			'rel': 'noopener'
		}, 'source');
	wrapElements(selector + ' .viewer', 'a', {
			'href': this.logViewerURL(path),
			'target': '_blank',
			'rel': 'noopener'
		}, 'source');
	wrapElements(selector + ' .inline', 'a', {
			'data-url': this.logViewerURL(path)
		}, 'source', createInlineViewer);
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
					'currentBuild.number': '.buildNumber',
					'currentBuild.build.port.revisionedName':
						'.revisionedName',
					'currentBuild.build.port.recipeFilePath':
						'.recipeFilePath'
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
			element.textContent = string;
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
					'port.revisionedName': '.revisionedName',
					'port.recipeFilePath': '.recipeFilePath'
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

	this.addLogs('#masterLog', 'master.log');
	this.addLogs('.builderName', 'builders/%s.log');
	this.addLogs('.buildNumber', 'builds/%s.log');

	wrapElements('#portsTreeHead', 'a', {
			'href': this.commitURL(),
			'target': '_blank',
			'rel': 'noopener'
		});
	wrapElements('.recipeFilePath', 'a', {
			'href': this.recipeFileURL(),
			'target': '_blank',
			'rel': 'noopener'
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
