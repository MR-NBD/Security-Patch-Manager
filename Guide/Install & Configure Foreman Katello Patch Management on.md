Katello Patch Management or foreman with Katello is one of the components of the upstream version of red hat satellite. Katello is a life cycle management plugin for Foreman . Katello allows managing thousands of machines in a a single click. It pulls content from remote repositories into an isolated environment and makes the subcription's management easy for us.
System Management Tool :
- Content Management 
- Host Provisioning 
- Configuration Management 
- Remote execution
- Patch/errata Management
- License Management
- Automation
- Alerts
- Identity and Policy 
- Reporting

The Red Hat Satellite version 5 based on SPacewalw, the current version of Satellite 6 is based on foreman with katello plugin. The most important core components are pulp, candlepin, qpid, puppet and much more.
![[image-1.png]]

**Foreman**
Foreman is an open source application used for provisioning and life cycle management of physical and virtual systems. Foreman automatically configures these systems using various methods, including kickstart and Puppet modules. Foreman also provides historical data for reporting, auditing, and troubleshooting.

**Katello**
Katello is a subscription and repository management application. It provides a means to subscribe to Red Hat repositories and download content. You can create and manage different versions of this content and apply them to specific systems within user-defined stages of the application life cycle.

**Candlepin**
Candlepin is a service within Katello that handles subscription management.

**Pulp**
Pulp is a service within Katello that handles repository and content management.

**Hammer**
Hammer is a CLI tool that provides command line and shell equivalents of most Web UI functions.

**REST API**
Red Hat Satellite 6 includes a RESTful API service that allows system administrators and developers to write custom scripts and third-party applications that interface with Red Hat Satellite.

**Capsule**
Red Hat Satellite Capsule Server acts as a proxy for some of the main Satellite functions including repository storage, `DNS`, `DHCP`, and Puppet Master configuration. Each Satellite Server also contains integrated Capsule Server services.

If you work on Red Hat satellite every day and need a similar environment in your home lab then go-head with Foreman with Katello. It provides a decent web interfaces exactly the same as Red Hat Satellite to Manage the physical and virtual servers(Content hosts) by provisioning, managing, patching etc.

## Basic OS setup
Before starting with foreman installation let is set up our server with basic configuration by assigning hostname, language settings and much more.
Set the locale before starting with the installation. Once completed with setting system locale to en-US.utf8 check the status.


Install chrony

chronyc sources

timedatectl set-ntp true
timedatectl status
firewall-cmd --add-port={53,80,443,5647,9090}/tcp --permanent
firewall-cmd -add-port={67-69,53}/udp --permanent
firewall-cmd --reload
lsblk
pvcreate /dev/sbd
vgcreate vg_pulp /dev/sbd
lvcreate -l 100%FREE -n lv_pulp vg_pulp
mkfs.xfs /dev/mapper/vg_pulp-lv_pulp

mkdir /var/lib/pulp
mount /dev/mapper/vg_pulp-lv_pulp /var/lib/pulp/

echo "/dev/mapper/vg_pulp-lv /var/lib/pulp xsf defaults 0 0" >> /etc/fstab 
tail -n1 /etc/fstab

restorecon -Rv /var/lib/pulp/
df -hP /var/lib/pulp/

yum update -y
roreman-rpm
katello-rpm
puppet
yum install foreman-release-scl -y
yum install katello -y


foreman-installer --scenario katello --foreman-initial-adim-username admin --foreman-initial-password 'password'

nano /etc/foreman-installer/scenarios.d/katello.yaml
- postgresql
- pulp
- candlepin
- qpid
- tftp
- dhcp
- apt
nano /etc/foreman-installer/scenarios.d/katello-answers.yaml
foreman::plugin::ansible: true

foreman-installer --scenario katello --foreman-initial-adim-username admin --foreman-initial-password 'password'

tail -f /var/log/foreman-installer/katello.log
katello-service status | grep -i "Active"


hammer user list
hammer organization list


create a product
- Name : name
- Labe : label
- -> save
hammer product create --organization-id 1 --name "name" --description "description"

 mkdir -p /etc/pki/rpm-gpg/import
![[image-2.png]]
GPG kwy form red hat

hammer gpg create --organization-id 1 --key "RPM-GPC-KEY-CentOS-7" --name "RPM-GPG-KEY-CentOS-7"

content Credential
create content credential

hammer repository create
![[image-3.png]]


environment list 
new environment
Create content view
Add repositories
Publish new version
New Activation Key

Associations -> conncet to hosts