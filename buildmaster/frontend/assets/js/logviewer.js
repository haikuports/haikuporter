'use strict';

var gSetAttributes = [];


function setAttribute(which, value)
{
	gSetAttributes = gSetAttributes.filter((value) => !value.startsWith(which));
	gSetAttributes.push(which + value);
}


function replaceAttributes(match, inner)
{
	const kAttributes = [
			'reset',
			'bright',
			'dim',
			'italic',
			'underscore',
			'blink',
			'blinkRapid',
			'reverse',
			'hidden',
			'crossed'
		];

	const kColors = [
			'black',
			'red',
			'green',
			'yellow',
			'blue',
			'magenta',
			'cyan',
			'white',
			'extended',
			'default'
		];

	var result = '';
	if (gSetAttributes.length > 0)
		result += '</span>';

	inner.split(';').forEach((attributeString) => {
			var attribute = Number.parseInt(attributeString || '0');
			if (attribute == 0)
				gSetAttributes = [];
			else if (attribute <= kAttributes.length)
				setAttribute(kAttributes[attribute], '');
			else if (attribute >= 30 && attribute <= 39)
				setAttribute('fg-', kColors[attribute - 30]);
			else if (attribute >= 40 && attribute <= 49)
				setAttribute('bg-', kColors[attribute - 30]);
		});

	if (gSetAttributes.length == 0)
		return result;

	return result + '<span class="' + gSetAttributes.join(' ') + '">';
}


function parseLogfile(content)
{
	const replacements = [
			{ what: '<', with: '&lt;' },
			{ what: '>', with: '&gt;' },
			{ what: '(\r\n)|\n|\r', with: '<br>' },
			{ what: '\t', with: '        ' },
			{ what: '  ', with: ' &nbsp;' },
			{ what: '\x1b((\\[K)|(\\(.))', with: '' },
			{ what: '\x1b\\[(([0-9]*;?)*)m', with: replaceAttributes }
		];

	document.body.textContent = 'parsing escape sequences';
	document.body.innerHTML = replacements.reduce((value, replace) => {
			return value.replace(new RegExp(replace.what, 'g'), replace.with);
		}, content);
	document.body.scrollTop = document.body.scrollHeight;
}


function init()
{
	var logfile = window.location.search.substring(1);
	if (logfile.length == 0) {
		document.body.textContent
			= 'no log file specified, specify as search parameter';
		return;
	}

	document.body.textContent = 'fetching "' + logfile + '"';
	fetch(logfile).then((response) => {
			if (!response.ok)
				throw response.status + ' ' + response.statusText;
			return response.text()
		}).then(parseLogfile, (error) => {
			document.body.textContent
				= 'failed to load logfile "' + logfile + '": ' + error;
		});
}

window.onload = init;
