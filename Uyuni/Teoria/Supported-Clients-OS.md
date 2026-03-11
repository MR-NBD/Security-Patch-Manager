## [Supported Client Systems](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/supported-features.html#supported-features-clients)
Client operating system is supported by the organization that supplies the operating system. The versions and SP levels must be under general support (normal or LTSS) to be supported with Uyuni. For details on supported product versions, see [https://www.suse.com/lifecycle](https://www.suse.com/lifecycle).

Supported client operating systems are listed in this table. The icons in the table indicate:

-  **✓** clients running this operating system are supported by SUSE
-  **x** clients running this operating system are not supported by SUSE
-  clients are under consideration, and may or may not be supported at a later date. (**NONE**)

| Operating System                            | x86-64 | ppc64le | IBM Z | aarch64 | arm64 / armhf |
| ------------------------------------------- | ------ | ------- | ----- | ------- | ------------- |
| SUSE Linux Enterprise 15, 12                | ✓      | ✓       | ✓     | ✓       | x             |
| SUSE Linux Enterprise Server for SAP 15, 12 | ✓      | ✓       | x     | x       | x             |
| SLE Micro                                   | ✓      | x       | x     | ✓       | x             |
| SL Micro                                    | ✓      | x       | x     | ✓       | x             |
| openSUSE Leap Micro                         | ✓      | x       | x     | ✓       | x             |
| openSUSE Tumbleweed                         | ✓      | x       | x     | ✓       | x             |
| openSUSE Leap 15                            | ✓      | x       | x     | ✓       | x             |
| Alibaba Cloud Linux 2                       | ✓      | x       | x     | ✓       | x             |
| AlmaLinux 9, 8                              | ✓      | x       | x     | ✓       | x             |
| Amazon Linux 2003, 2                        | ✓      | x       | x     | ✓       | x             |
| CentOS 7                                    | ✓      | ✓       | x     | ✓       | x             |
| Debian 12 (*)                               | ✓      | x       | x     | x       | x             |
| openEuler 22.03                             | v      | x       | x     | x       | x             |
| Open Enterprise Server 24.4, 23.4           | ✓      | x       | x     | x       | x             |
| Oracle Linux 9, 8, 7                        | ✓      | x       | x     | ✓       | x             |
| Raspberry Pi OS 12                          | x      | x       | x     | x       | ✓             |
| Red Hat Enterprise Linux 9, 8, 7            | ✓      | x       | x     | x       | x             |
| Rocky Linux 9, 8                            | ✓      | x       | x     | ✓       | x             |
| Ubuntu 24.04, 22.04, 20.04 (*)              | ✓      | x       | x     | x       | x             |
**(\*) Debian and Ubuntu list the x86-64 architecture as amd64.**

When the distibution reaches end-of-life, it enters grace period of 3 months when the support is considered deprecated. After that period, the product is considered unsupported. Any support may only be available on the best-effort basis.

For more information about end-of-life dates, see [https://endoflife.software/operating-systems](https://endoflife.software/operating-systems).