# Security

## Reporting a problem

Report security problems privately: on GitHub, open the **Security** tab of this repository and
choose **Report a vulnerability**. Please don't open a public issue for them.

Say what you found, how to reproduce it, and which version or commit you used. You should get a
reply within a week.

## Supported versions

Only the latest release gets fixes. art98 runs from a checkout, so a fix lands on `main` and in
the next release.

## What counts

The VM service is the part that matters. A client that holds the token can make the guest run
any Win32 call: that is how art98 works, not a flaw. So these are in scope:

- connecting to the VM service without the token, or reading the token without access to its
  file;
- the published ports (`control`, `vnc`) listening anywhere other than `[ports] bind`, which is
  `127.0.0.1` by default;
- a state file running code, or the guest or the container reaching the host in a way the docs
  don't describe;
- anything that would put files from `work/` (installed copies of Windows) into the repository
  or a release.

Out of scope: scene files, which are Python run on your machine like any other script; what a
token holder can do inside the guest; a `bind` you set to an address other
machines can reach; and Windows 98 itself. Windows 98 product keys are public and are not
secrets. See [configuration](docs/setup/config.md) and
[the VM service](docs/design/container.md#the-vm-service).
