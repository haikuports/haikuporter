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
    * Storage for various required sources like haikuports or haiku
  * /var/packages
    * Storage for packages (TODO, more info)
  * /var/buildmaster
    * Main state directory for buildmaster
    * haikuports
      * buildmaster
        * builders
        * haikuports.conf
