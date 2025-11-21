ifconfig 
hostname 
sudo su 
nano /etc/hosts
<IP> <MY-HOSTNAME>.localdomain <MY-HOSTANME>
sudo dnf clean all
sudo dnf update -y
sudo reboot
cat /etc/os-release
rpm -q selinux-policy
Devi avere una versione del tipo:

`selinux-policy-38.1.53-5.el9_6`

Stai usando **RHEL 9.4**, ma i pacchetti SELinux di Foreman/Katello che stai installando richiedono:

- `selinux-policy >= 38.1.45-3.el9_5`
    
- `selinux-policy >= 38.1.53-5.el9_6`
    

La tua versione è:

`selinux-policy-38.1.35-2.el9_4.4  ← troppo vecchia`
sudo subscription-manager register
sudo subscription-manager attach --auto
sudo subscription-manager repos --enable=rhel-9-for-x86_64-baseos-rpms
sudo subscription-manager repos --enable=rhel-9-for-x86_64-appstream-rpms
sudo dnf upgrade --releasever=9.6 -y
sudo reboot

## Firewall Settings

# firewall-cmd --add-port="5646/tcp"  
# firewall-cmd \  
--add-port="5647/tcp" \  
--add-port="8000/tcp" \  
--add-port="9090/tcp"  
  
# firewall-cmd \  
--add-service=dns \  
--add-service=dhcp \  
--add-service=tftp \  
--add-service=http \  
--add-service=https \  
--add-service=puppetmaster  
  
# firewall-cmd --runtime-to-permanent

>  **check if it works <<**

# firewall-cmd --list-all


https://docs.theforeman.org/3.15/Quickstart/index-katello.html

## Configuring repositories

Procedure

1. Clear any metadata:
    
    # dnf clean all
    
2. Install the `foreman-release.rpm` package:
    
    # dnf install https://yum.theforeman.org/releases/3.15/el9/x86_64/foreman-release.rpm
    
3. Install the `katello-repos-latest.rpm` package:
    
    # dnf install https://yum.theforeman.org/katello/4.17/katello/el9/x86_64/katello-repos-latest.rpm
    
4. Install the `puppet-release` package.
    
    - For Puppet 8:
        
        # dnf install https://yum.puppet.com/puppet8-release-el-9.noarch.rpm
    

Verification

- Verify that the required repositories are enabled:
    
    # dnf repolist enabled

## Installing Foreman server packages

Procedure

1. Update all packages:
    
    # dnf upgrade
    
2. Install `foreman-installer-katello`:
    
    # dnf install foreman-installer-katello


## Running the Foreman installer

The installation run is non-interactive, but the configuration can be customized by supplying any of the options listed in `foreman-installer --help`, or by running `foreman-installer -i` for interactive mode. More examples are described in the `Installation Options` section. The `-v` option disables the progress bar and displays all changes.

Procedure

- Run the Foreman installer:
    
    # foreman-installer --scenario katello
    

The script displays its progress and writes logs to `/var/log/foreman-installer/katello.log`.

