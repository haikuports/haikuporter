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

  * /var/sources
    * Storage for various required sources like haiku
  * /var/packages
    * Storage for packages and repositories
  * /var/buildmaster
    * Main state directory for buildmaster
    * output
      * records - json dump of internal haikuporter state data during buildrun. Symlinks to buildruns
      * builds - logs of buildruns. Symlinks to buildruns
      * buildruns - complete log of every buildrun and build
    * haikuports
      * buildmaster
        * builders
        * haikuports.conf
