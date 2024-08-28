# HaikuPorter in Buildmaster mode

One buildmaster container per architecture

# Requirements

## Secrets

  * ```/run/secrets/sig_repo_privatekey``` - Minisign private key to sign repos (optional)
  * ```/run/secrets/sig_repo_privatekeypass``` - Password for Minisign private key (optional)

## Environmental

  * ```BUILD_TARGET_ARCH``` - Target architecture for buildmaster
  * ```SYSTEM_PACKAGE_BRANCH``` - The branch of the system packages
    * system-packages are expected at /var/buildmaster/system-packages/$SYSTEM_PACKAGE_BRANCH
  * ```STORAGE_BACKEND_CONFIG``` - The path of an external storage backend json config file (optional)
    * example: ```{"backend_type": "s3", "endpoint_url": "", "access_key_id": "", "secret_access_key": "", "bucket_name": ""}```
    * Fields:
      * backend_type - s3 for now (required)
      * prefix - prefix path of repository (optional)
      * endpoint_url - s3 endpoint url
      * access_key_id - s3 access key id
      * secret_access_key - s3 secret access key
      * bucket_name - s3 bucket name
  * ```REPOSITORY_TRIGGER_URL``` - Target URL to hit when build complete (optional)
    * example: https://depot.haiku-os.org/__repository/haikuports/source/haikuports_x86_64/import

## Volumes

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

* haikuporter buildmaster builds packages into /var/buildmaster/haikuports/packages which quietly goes to /var/packages/instances/master/(arch) via a symlink
  * This follows the basic haikuporter behaviour
* haikuporter buildmaster then moves obsolete packages from /var/buildmaster/haikuports/packages /var/buildmaster/haikuports/packages/.obsolete/ (keeping in mind packages is a symlink)
  * This follows the basic haikuporter behaviour
* haikuporter buildmaster then hardlinks packages in /var/packages/instances to /var/packages/repository/(branch)/(arch)/current/packages/
  * This is something performed by haikuporter --create-package-repository called by loop
* haikuporter buildmaster then generates a repository for the hardlinked packages in /var/packages/repository/(branch)/(arch)/current/
  * This is something performed by haikuporter --create-package-repository called by loop
