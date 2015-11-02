# rebel

A collection of APIs and corresponding CLIs to automate deployment of Pivotal Cloud Foundry.
Ultimately, I hope to wrap these into a coherent utility for automated, unattended installation
of Pivotal Cloud Foundry on AWS, and maybe other infrastructures in future.

Even in their current, incomplete state, the tools really ease AWS deployment of PCF, so I
decided to share them in their current form. A complete AWS deployment workflow consists of
just a couple of simple steps:

1. Create a rebel.cfg file in your current directory with the following entries:
```
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
cf config <your-stack-name>
opsmgr.y install <your-stack-name>
```

## Individual Command Line References

### Pivotal Network (pivnet.py)

```
products [<product-name>]
releases <product-name> [<release-name>]
accept-eula <product-name> <release-name>
files <product-name> <release-name> [<file-name>]
download <product-name> <release-name> [<file-name>]
```
