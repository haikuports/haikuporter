# HaikuPorter in Buildmaster mode

One buildmaster container per architecture

# Requirements

## Secrets

  * ```/run/secrets/sig_repo_privatekey``` - Minisign private key to sign repos (optional)
  * ```/run/secrets/sig_repo_privatekeypass``` - Password for Minisign private key (optional)

## Environmental

  * ```BUILD_TARGET_ARCH``` - Target architecture for buildmaster
  * ```REPOSITORY_TRIGGER_URL``` - Target URL to hit when build complete (optional)
    * example: https://depot.haiku-os.org/__repository/haikuports/source/haikuports_x86_64/import

## Volumes

  * /var/sources (shared between all architectures)
    * Storage for various required sources like haiku
  * /var/packages (shared between all architectures)
    * Storage for packages and repositories
    * repository
      * Haikuports repositories
    * instances
      * Has all built packages
      * A symlink from /var/buildmaster/haikuports/packages
      * Packaged hardlinked into /var/packages/repository/(branch)/(arch)/current/packages/
  * /var/buildmaster (one-per-architecture)
    * Main state directory for buildmaster
    * output
      * records - json dump of internal haikuporter state data during buildrun. Symlinks to buildruns
      * builds - logs of buildruns. Symlinks to buildruns
      * buildruns - complete log of every buildrun and build
    * haikuports
      * buildmaster
        * builders
        * haikuports.conf

## Repository generation

> aka our Rube Goldberg machine

* haikuporter buildmaster builds packages into /var/buildmaster/haikuports/packages which quietly goes to /var/packages/instances/master/(arch) via a symlink
  * This follows the basic haikuporter behaviour
* haikuporter buildmaster then moves obsolete packages from /var/buildmaster/haikuports/packages /var/buildmaster/haikuports/packages/.obsolete/ (keeping in mind packages is a symlink)
  * This follows the basic haikuporter behaviour
* haikuporter buildmaster then hardlinks packages in /var/packages/instances to /var/packages/repository/(branch)/(arch)/current/packages/
  * This is something performed by haikuporter.py --create-package-repository called by loop
* haikuporter buildmaster then generates a repository for the hardlinked packages in /var/packages/repository/(branch)/(arch)/current/
  * This is something performed by haikuporter.py --create-package-repository called by loop
