# rebel

A collection of APIs and corresponding CLIs to automate deployment of Pivotal Cloud Foundry.
Ultimately, I hope to wrap these into a coherent utility for automated, unattended installation
of Pivotal Cloud Foundry on AWS, and maybe other infrastructures in future.

Even in their current, incomplete state, the tools really ease AWS deployment of PCF, so I
decided to share them in their current form. A complete AWS deployment workflow consists of
just a couple of simple steps:

*At this time the tools are known to work with PCF 1.6 without changes. Other versions likely
need some changes to the scripts. I intend to support all versions going forward, and maybe add
back-level support for 1.5 (that's where rebel started).*

1. Create a rebel.cfg file in your current directory with the following contents:
  ```
  [pivotal-network]
  token = <your-pivnet-access-token>

  [aws]
  ssl-certificate-arn = <your-certificate-arn>
  nat-key-pair = <your-key-pair-name>
  rds-username = <username-of-your-choosing>
  rds-password = <password-of-your-choosing>
  private-key = <path-to-your-private-key-pem-file>
  system-domain = <your-domain>
  apps-domain = <your-domain>
  ```

2. Execute the following commands

  ```
  aws.py configure
  pivnet.py accept-eula "Elastic Runtime" <pcf-version>
  cloudformation.py create-stack <your-stack-name> <pcf-version>
  opsmgr.py launch <your-stack-name>
  ```

  This will do a number of things for you (unless they were already done):
  - Download and install a private copy of the AWS command line
  - Download the proper version of the CloudFormation template from PivNet
  - Populate that template and execute it
  - Capture the output values
  - Start an Ops Manager VM from the correct AMI image for the region you are using
  - Configure Ops Manager Director (BOSH) using the CloudFormation outputs

  After this, if you were to log in to the Ops Manager instance (you can but don't need to!)
  you will see a *green* (i.e. fully configured) Director tile. You can install it and take
  it manually frome here, or proceed to set up the Elastic Runtime:

3. Manually configure your DNS provider as instructed by the output of the previous steps

  Assuming all goes well, the second command above will give you the Ops Manager URL and password, as well as
  the DNS names for your PCF domain that you will need to create CNAME records for (if you don't, the
  final install step will fail)

4. Complete the installation

  ```
  cf.py config <your-stack-name> <pcf-version>
  opsmgr.py install <your-stack-name>
  ```
  
  This will:
  - Download (directly from S3 to the Ops Manager VM) the Elastic Runtime tile
  - Add it to the Ops Manager installation
  - Configure it (so it goes *green*)
  - Install everything that is queued to be installed (Director and Elastic Runtime)
  - Tail the logs to your console

## Individual Command Line References

Each of the individual modules implements a nicely consumable set of Python APIs. But to
exercise those APIs, I also added a CLI implementation to each of them. Those CLIs are
directly consumable for a variety of purposes. Here is the entire collection.

### Pivotal Network (pivnet.py)

```
products [<product-name>]
releases <product-name> [<release-name>]
accept-eula <product-name> <release-name>
files <product-name> <release-name> [<file-name>]
download <product-name> <release-name> [<file-name>]
```

These commands will:
- List all products available on PivNet (optionally accepting a partial name as filter)
- List all releases available for a given product (optionally accepting a partial version number as filter)
- Accept the EULA for a specified release (required before downloading any files)
- List all the files for a given release
- Download specified files

### CloudFormation (cloudformation.py)

```
create-stack <stack-name> [<release>]
delete-stack <stack-name>
stacks [<stack-name>]
outputs <stack-name>
resources <stack-name>
template [<release>]
```

These commands will:
- Create an AWS stack of the given name (must be unique) using the template of the given version (latest GA is default)
- Delete the stack of the given name (I actually recommend using "cleanup.py stack <stack-name>" instead, see below)
- List the stacks you've created
- List the CloudFormation outputs for the given stack
- List the AWS resources that were created for the given stack
- Show the template for the specified release (latest GA is default)

### Ops Manager (opsmgr.py)

```
launch <stack-name> [<version>]
terminate <stack-name>
instances
images [<region>]
logs <stack-name>
settings <stack-name>
products <stack-name>
import <stack-name> <product-name> <release-name>
install <stack-name>
uninstall <stack-name>
```

### Ops Manager Director (bosh.py)

```
config <stack-name>
```

### Elastic Runtime (cf.py)

```
config <stack-name> [<version>]
```

### Cleanup (cleanup.py)

**USE WITH EXTREME CAUTION**

```
vpc <vpc-id>
stack <stack-name>
all
```

Removes (deletes/terminates) the named AWS resources *and all their dependencies*. This is powerful and hence somewhat dangerous. But it's a lot more efficient than trying to use CloudFormation to delete a stack, especially after you have
created additional dependencies that are not managed by CloudFormation. You can specify a specific VPC, a CloudFormation
stack, or "all". The latter will also wipe out *all your S3 buckets*!!!.

**USE WITH EXTREME CAUTION**
