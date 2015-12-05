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


function BuildMaster()
{
	this.fetchStatus();
}


BuildMaster.prototype.fetchStatus = function()
{
	var request = new XMLHttpRequest();
	request.open('GET', 'output/status.json');
	request.onreadystatechange = function() {
			if (request.readyState != 4)
				return;

			if (request.status == 200)
				this.status = JSON.parse(request.responseText);
			else {
				this.status = {
						'status': 'failed to load: ' + request.status
					};
			}

			this.showStatus();
		}.bind(this);

	request.send(null);
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
					'lost': '.builderLost',
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
		};

	addBuilderList('#builders', this.status.builders);

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

	wrapElements('.buildNumber', 'a',
		{ 'href': 'output/builds/%s.log', 'target': '_blank' });
	wrapElements('.builderName', 'a',
		{ 'href': 'output/builders/%s.log', 'target': '_blank' });

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
