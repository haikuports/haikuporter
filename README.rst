Setting up the correct environment
==================================


Configure your editor
---------------------

Whitespace plays is significant in Python so it's essential that everyone on a project observes the same rules. In general, in Python projects editors are configured always to use spaces instead of tabs and to strip any trailing whitespace.

In addition, it's possible to set up the VCS to enforce but only on a per user basis. A sample setup:

* Create a .gitattributes file at the head of the repository and add the following line:
`*.py filter=fix_whitespace`

* Add the filter to the .git/config:
``
[filter "fix_whitespace"]
    clean = expand -t 4
    smudge = expand -t 4
    required
[merge]
    renormalize = true`
``


Key here are the tools expand and unexpand. Unfortunately, their names and parameters from platform to platform.

* Run the changes locally: `git checkout HEAD -- **`


Installing in a development environment
---------------------------------------


It is common to develop projects in a virtual environment "virtualenv" which is insulates the project from the system install and vice-versa. Haiku's support for this is currently limited.

In the checkout folder create a virtualenv:
`virtualenv .`

You can "activate" this environment with the following command:
`source bin/activate`

This manipulates some environment variables which some people like to avoid. You exit the virtualenv with the "deactivate" command.


Add the test tools
++++++++++++++++++


pytest is the test framework. Python comes with unit test support but many Python people prefer pytest because it does not remind them of Java! pytest can run unit tests which is great on existing projects. The much more Pythonic syntax and test discovery are the main differences to unit test

In your virtualenv:

`pip install pytest`

Then run your tests:

`py.test -rf HaikuPorter`

There is also a profile test coverage statistics:

`py.test --cov=HaikuPorter`


Additional tools
++++++++++++++++

Support for running the tests in different conditions is provided by tox. Support for coverage information is provided by pytest-cov.

You can install a common set:

`pip install -U -r requirements.txt`


Documentation
-------------


There is now support for Sphinx-based documentation. This is best generated using the tox profile:

`tox -e doc`

The documentation will be generated into the html folder.
