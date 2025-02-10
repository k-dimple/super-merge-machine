# ESM introduction

Gabriel-AN | 2024-02-07 09:49:39 UTC | #1

# Background

As part of [Ubuntu Pro](https://ubuntu.com/pro/beta) for Applications subscription, [ROS ESM](https://ubuntu.com/robotics/ros-esm) gives you a hardened and long-term supported ROS system for robots and its applications. Even if your ROS distribution hasn’t reached its end-of-life (EOL), you can count on backports for critical security updates and CVEs fixes for your environment. In addition, all upstream changes are evaluated by hand to minimise breaking changes. By enabling our repositories, you will get trusted and stable binaries for your environment. If you are a standard or advanced customer, you also get ROS support. This provides you with a single point of contact to log ROS bugs.

## Benefits

ROS ESM provides four key benefits:

* 10 year LTS release lifetime for ROS bringing the highest level of security and compliance
* Security patching for over 25,000 packages in ROS, Ubuntu Universe and Ubuntu main
* Better security KPIs as critical CVEs patches are applied on average in less than 24h
* Single point of contact to log bugs and propose fixes to guarantee timely and quality fixes

For more information, please visit [Ubuntu Pro Service Description, Extended Security Maintenance (ESM) page,](https://ubuntu.com/security/esm) and [ROS ESM Specialist service description](https://ubuntu.com/legal/ubuntu-pro-description/ros-esm-service-description). Or [contact us for more information](https://ubuntu.com/robotics/ros-esm#get-in-touch).

# How to enable ROS ESM

ROS ESM builds on two Canonical ESM products: ESM-infra and ESM-apps. As a result, there are three steps to enabling ROS ESM:

1. Obtaining your token
2. Enabling ESM-infra and ESM-apps
3. Enabling ROS ESM.

Note that ESM-infra and ESM-apps are required dependencies of ROS ESM.

## Obtain your authentication token

Access to ESM is controlled by a token associated with your Ubuntu Single Sign-on (SSO) account. If you already purchased ROS ESM, then you will have the token and you can review it on:

https://ubuntu.com/pro

Ubuntu Advantage is now Ubuntu Pro. Ubuntu Pro expands our famous ten-year security coverage to an additional 23,000 packages beyond the main operating system.

If you haven’t purchased ROS ESM yet, please [contact us ](https://ubuntu.com/robotics/ros-esm#get-in-touch)and a sales representative will get in touch with you.

## Enabling ESM-infra and ESM-apps

In order to enable these services, you will need:

* An Ubuntu LTS machine with a version similar to or above 16.04 LTS
* Sudo access
* An email address, or an existing Ubuntu One account
* Ubuntu Pro client version 27.11.2 or newer

Once you have your contract token, make sure your Pro client is up to date:

```
$ sudo apt update && sudo apt upgrade
$ sudo apt install -y ubuntu-advantage-tools
```

For more information, please visit [Ubuntu Pro Client Guide](https://discourse.ubuntu.com/t/ubuntu-pro-client/31027).

### Confirm your Ubuntu Pro client version

Regardless of your Ubuntu distribution, make sure you are running the latest version of the Ubuntu Pro client. To check it, run:

```
$ sudo pro --version
```
You should have a version greater than or equal to 27.11.2.

### Attach the Pro client

Use the client to attach this machine to your contract using your token:

```
$ sudo pro attach YOUR_TOKEN
```
Note, if you had previously attached a UA token, you might see a message like this:

```
This machine is already attached to YOUR_EMAIL
To use a different subscription first run: sudo pro detach.
 ```

In that case, detach your token as indicated, and try attaching your Ubuntu Pro token again.

You should see some of the Ubuntu Pro services, such as Expanded Security Maintenance for Infrastructure (esm-infra) automatically enabled, while others will remain disabled until you switch them on. You can check this with:

```
$ sudo pro status
```
If it’s not, enter the following:
```
$ sudo pro enable esm-infra
```
Then, enable ESM Apps with:
```
$ sudo pro enable esm-apps --beta
```
At any time, you can check how many deb packages are installed on your machine and from which source using: 
``` 
$ pro security-status
```
Congratulations, you now have ESM-infra and ESM-apps enabled! Run an upgrade to install available security updates, if any:

```
$ sudo apt update
$ sudo apt upgrade
```

More information at: https://ubuntu.com/security/esm

## Enabling ROS ESM

ROS ESM is exposed in the Pro client similar to ESM-infra and ESM-apps and is controlled by that same token. However, ROS ESM is disabled by default and not listed in the common service list. First, let’s make sure that the Pro client is up-to-date:

```
$ sudo pro version
```
Should return version 27.11.2 or greater.

Then, let’s make sure that your token is entitled to enabling ROS ESM with:

```
$ sudo pro status --all
```

You should now see the following ROS ESM services: ‘ros’ and ‘ros-updates’. Make sure that the ‘entitled’ column displays a ‘yes’ in front of these services.  If not, please reach out to customer service as shown in your welcome email.

Now you have everything needed to enable ROS ESM. There are two suites available:

* **ros**: only security-related updates for ROS-related software.
* **ros-updates**: security and non-security-related updates for ROS-related software. These are security updates and bug fixes.

**To enable the ROS security updates**, run the following command:

```
$ sudo pro enable ros --beta
```

**To enable non-security updates**, run the following command:

```
$ sudo pro enable ros-updates --beta
```

Note that if you enter directly:

```
$ sudo pro enable ros-updates --beta
```

You will be prompted to enable the ‘ros’ service first, as ‘ros-updates’ depends on ‘ros’.

# Using ROS ESM

Congratulations, you’re now set up to use ROS ESM! From there, you can either install the complete ROS distro variant offered by ROS ESM (ros_base), or you can use rosdep to install the specific dependencies required by your ROS project. Let's quickly explore both options.

## Installing ROS ESM base variant

ROS ESM offers the upstream metapackage variant called ros_base, which facilitates the installation of all ROS packages included in this variant.  For example, if you are working with Xenial and its corresponding version ROS Kinetic, run the command:

```
$ sudo apt install ros-kinetic-ros-base
```

> :information_source:  You have to remember that the Ubuntu version and ROS version are co-dependent, so you have to choose a pair. For example, Ubuntu 16.04 LTS and ROS Kinetic, Ubuntu 18.04 LTS and ROS Melodic, Ubuntu 20.04 LTS and ROS 2 Foxy. Here you can find more information for [ROS distributions](http://wiki.ros.org/Distributions) and [ROS 2 distributions](https://docs.ros.org/en/foxy/Releases.html).

## Note on rosdep set up

Note that ROS ESM is its own ROS distribution, and thus provides its own distribution and rosdep files. If you already have upstream ROS installed and initialized (e.g. you previously ran `sudo rosdep init`), you’ll need to make sure you install rosdep from ESM. and Re-initialise it as follows:

```
$ sudo apt install python-rosdep
$ sudo rm /etc/ros/rosdep/sources.list.d/20-default.list
$ sudo rosdep init
$ rosdep update
```

## Installing ROS ESM project-specific dependencies

Typically, when utilizing ROS ESM, your ROS workspace would already be configured with the relevant source code. In such cases, it is highly recommended to accurately define the dependencies of your packages in the package.xml file and proceed by installing all the required ROS ESM dependencies by executing the following command:

```
$ cd ros-ws
$ rosdep install –ignore-src –from-paths src
```

By doing so, the packages required for your project will be fetched and installed from the ROS ESM ppa, ensuring smooth operation.

# ESM and non-ESM components

A given ROS distribution includes a huge number of packages with wildly varying levels of quality. ROS ESM does not attempt to support them all (such a thing would be disingenuous), and instead focuses on core functionality. Besides, it’s not unusual for upstream ROS components to break backward compatibility, while ESM will not. One ramification of this is that ROS packages in ESM might fall behind their upstream counterparts in order to retain stability.

We of course realise that everyone’s needs are different, and are very open to receiving feedback about anything that should be added to ROS ESM. While such additions will need to pass some scrutiny, we fully expect the number of ROS packages included in ESM to grow over time.


## Combining ESM and upstream ROS components

We don't support enabling both ROS ESM as well as the upstream ROS Debian repository. This means that every ROS component you use must either be from ESM, or built from source against ESM.

There is tooling that makes this fairly straightforward, called rosinstall_generator, that will generate a rosinstall file containing the desired package(s) and all dependencies not already satisfied.

In a sourced ROS ESM environment, execute the following:

```
$ sudo apt install python-rosinstall-generator
$ export ROSDISTRO_INDEX_URL="https://raw.githubusercontent.com/ros/rosdistro/master/index-v4.yaml"
$ rosinstall_generator <package>  --rosdistro <ros-distro>  --deps-up-to RPP > ~/extra-stuff.rosinstall
```

For example:
```
$ rosinstall_generator desktop_full --rosdistro kinetic --deps-up-to RPP > ~/extra-stuff.rosinstall
```

Once that file is obtained, there are a few steps left to have the software usable.

First, if there isn’t a workspace already, this needs to be created:

```
$ mkdir -p ~/ros_ws/src
```

If not already installed, install wstool with the following command:
```
sudo apt-get install python-wstool
```

Then the repos in the rosinstall file need to be fetched into the workspace with the following command: 
```
$ cd ~/ros_ws
$ wstool init src ~/extra-stuff.rosinstall
```

Now dependencies of the workspace need to be installed:

```
$ cd ~/ros_ws
$ rosdep install --ignore-src --from-paths src
```

Finally, the workspace needs to be built:

```
$ cd ~/ros_ws
$ catkin_make_isolated
```
That builds the required software against the ESM ROS release, where ABI will not break. Once the process is complete, the required software is available in the workspace.

> :information_source: Since ROS Groovy not all packages belonging to the desktop_full metapackage have been catkinized. As a result, when using rosinstall generator it is necessary to compile the workspace using catkin_make_isolated.