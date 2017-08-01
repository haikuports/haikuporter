function loadJSON(callback) {   
	var xobj = new XMLHttpRequest();
	xobj.overrideMimeType("application/json");
	xobj.open('GET', 'buildruns/output/status.json', true);
	xobj.onreadystatechange = function () {
		if (xobj.readyState == 4 && xobj.status == "200") {
			// Required use of an anonymous callback as .open will NOT return a value but simply returns undefined in asynchronous mode
			callback(xobj.responseText);
		}
	};
	xobj.send(null);  
}

loadJSON(function(response) {
	// Parse JSON string into object
	var data = JSON.parse(response);

	//var raw = document.createElement("pre");
	//raw.innerHTML = JSON.stringify(data, null, 2);

	var builders = document.createElement("table");
	builders.innerHTML = "<tr><th>Builder</th><th>Online</th><th>Job</th></tr>";
	for(i = 0; i < data.builders.active.length; i++)
	{
		builder = data.builders.active[i];
		if (builder.currentBuild) {
			port = builder.currentBuild.build.port.revisionedName;
		} else {
			port = "Idle."
		}
		builders.innerHTML += "<tr><td>" + builder.name + "</td><td>" +
			!builder.lost + "(" + builder.connectionErrors + "/" + builder.maxConnectionErrors +  ")</td><td>" + port + "</td></tr>"
	}
	for(i = 0; i < data.builders.lost.length; i++)
	{
		builder = data.builders.lost[i];
		builders.innerHTML += "<tr><td>" + builder.name + "</td><td>" +
			!builder.lost + "(" + builder.connectionErrors + "/" + builder.maxConnectionErrors +  ")</td><td><a href=\"current/output/builders/" + builder.name + ".log\">log</a></td></tr>"
	}

	var builds = document.createElement("table");
	builds.innerHTML = "<tr><th>Build</th><th>Status</th></tr>";
	for (i = 0; i < data.builds.failed.length; i++)
	{
		build = data.builds.failed[i]
		builds.innerHTML += '<tr class="failed"><td>' + build.port.revisionedName + "</td><td>"
			+ '<a href="current/output/builds/' + build.buildNumbers[0] + '.log">FAILED</a>' + "</td></tr>"
	}

	for (i = 0; i < data.builds.complete.length; i++)
	{
		build = data.builds.complete[i]
		builds.innerHTML += '<tr class="complete"><td>' + build.port.revisionedName + "</td><td>"
			+ '<a href="current/output/builds/' + build.buildNumbers[0] + '.log">complete!</a>' + "</td></tr>"
	}

	for (i = 0; i < data.builds.active.length; i++)
	{
		build = data.builds.active[i]
		builds.innerHTML += '<tr class="active"><td>' + build.port.revisionedName + "</td><td>"
			+ "building…" + "</td></tr>"
	}

	for (i = 0; i < data.builds.scheduled.length; i++)
	{
		build = data.builds.scheduled[i]
		builds.innerHTML += '<tr class="scheduled"><td>' + build.port.revisionedName + "</td><td>"
			+ "pending" + "</td></tr>"
	}

	for (i = 0; i < data.builds.blocked.length; i++)
	{
		build = data.builds.blocked[i]
		builds.innerHTML += '<tr class="blocked"><td>' + build.port.revisionedName + "</td><td>"
			+ JSON.stringify(build.missingPackageIDs, null, 2) + "</td></tr>"
	}


	var pth = document.createElement("p");
	pth.innerHTML = "Haikuports revision " + data.portsTreeHead + ". " + data.buildStatus;

	var base = document.getElementById('status')

    while (base.firstChild) {
		base.removeChild(base.firstChild);
	}

	base.appendChild(pth);
	base.appendChild(builders);
	base.appendChild(builds);
});

