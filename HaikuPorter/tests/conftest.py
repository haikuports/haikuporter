import pytest


@pytest.fixture
def DummyConfiguration(monkeypatch):
	from .. Configuration import  Configuration
	def do_nothing(self):
		pass
	monkeypatch.setattr(Configuration, "_readConfigurationFile", do_nothing)
	Configuration.init()
	return Configuration
