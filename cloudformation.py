#!/usr/bin/env python

import sys
import pivnet
import config
import json
import aws
import cli
import time, datetime

""" CloudFormation API """

def download_template(version, verbose=False):
	version = config.get('elastic-runtime', 'release', None) if version is None else version
	product = pivnet.pivnet_select_product('Elastic Runtime')
	release = pivnet.pivnet_select_release(product, version)
	version = release["version"]
	files   = pivnet.pivnet_files(product, release, 'cloudformation')
	if len(files) < 1:
		print "no cloudformation template found for release", version
		sys.exit(1)
	if len(files) > 1:
		print "multiple cloudformation templates found for release", version
		sys.exit(1)
	if verbose:
		print "Downloading CloudFormation template for Elastic Runtime version", version
	template = json.load(pivnet.pivnet_open(files[0]))
	metadata = {
		"created-by": "ramble",
		"pcf-version": version,
	}
	template["Metadata"] = metadata
	return template

def list_stacks(stack_pattern = ""):
	stacks = json.loads(aws.aws_cli_verbose(['cloudformation', 'describe-stacks']))["Stacks"]
	stacks = [s for s in stacks if is_ramble_stack(s)]
	stacks = [s for s in stacks if stack_pattern in s["StackName"]]
	return stacks

def select_stack(stack_pattern):
	stacks = list_stacks(stack_pattern)
	if len(stacks) < 1:
		print stack_pattern, "does not match any stacks. Available stacks are:"
		print "\n".join(["   " + s["StackName"] for s in list_stacks()])
		sys.exit(1)
	if len(stacks) > 1:
		print stack_pattern, "matches multiple stacks:"
		print "\n".join(["   " + s["StackName"] for s in stacks])
		print "Please be more specific"
		sys.exit(1)
	return stacks[0]

def get_stack(stack_id):
	stacks = json.loads(aws.aws_cli_verbose(['cloudformation', 'describe-stacks', '--stack-name', stack_id]))["Stacks"]
	if len(stacks) < 1:
		print stack_pattern, "does not match any stacks. Available stacks are:"
		print "\n".join(["   " + s["StackId"] for s in list_stacks()])
		sys.exit(1)
	return stacks[0]

def create_stack(template, name, sync=True, verbose=False):
	command = [
		'cloudformation',
		'create-stack',
		'--stack-name', name,
		'--template-body', json.dumps(template),
		'--on-failure', 'DO_NOTHING',
		'--parameters', json.dumps(get_parameters(template)),
		'--capabilities', 'CAPABILITY_IAM',
		'--tags', json.dumps(set_tags(template))
	]
	aws.aws_cli_verbose(command)
	if sync:
		await_stack(name, verbose)

def delete_stack(stack, sync=True, verbose=False):
	name = stack["StackName"]
	command = [
		'cloudformation',
		'delete-stack',
		'--stack-name', name
	]
	aws.aws_cli_verbose(command)
	if sync:
		await_stack(name, verbose)
	config.remove_section("stack-" + name)

def await_stack(name, verbose=False):
	""" Wait for in-progress state to clear """
	starttime = datetime.datetime.now()
	stack = select_stack(name)
	in_progress = True
	resources = {}
	while in_progress:
		in_progress = update_stack_resources(stack, resources, starttime, verbose)
		time.sleep(5)

def update_stack_resources(stack, oldresources, starttime, verbose=False):
	stack_id = stack["StackId"]
	stack_status = get_stack(stack_id)["StackStatus"]
	in_progress = stack_status.endswith("_IN_PROGRESS")
	if verbose:
		line_length = 120
		blank_line = ' ' * line_length + '\r'
		operation = friendly_status(stack_status)
		partials = []
		newresources = get_stack_resources(stack_id)
		since = datetime.datetime.now() - starttime
		for newresource in newresources:
			resource_id = newresource["LogicalResourceId"]
			newstatus   = newresource["ResourceStatus"]
			oldresource = oldresources.get(resource_id, None)
			if newstatus.endswith("_IN_PROGRESS"):
				partials.append(resource_id)
			elif oldresource is not None and oldresource["ResourceStatus"] != newstatus:
				sys.stdout.write(blank_line)
				print friendly_delta(since), friendly_status(newstatus), resource_id
			oldresources[resource_id] = newresource
		if len(partials) > 0:
			partials_line = friendly_delta(since) + " " + operation + " " + ", ".join(partials)
			partials_line = (partials_line[:line_length - 3] + '...') if len(partials_line) > line_length else partials_line
			sys.stdout.write(blank_line)
			sys.stdout.write(partials_line + '\r')
			sys.stdout.flush()
	return in_progress

def get_stack_resources(stack_id):
	resources = json.loads(aws.aws_cli_verbose(['cloudformation', 'list-stack-resources', '--stack-name', stack_id]))["StackResourceSummaries"]
	for resource in resources:
		if resource["ResourceType"] == 'AWS::CloudFormation::Stack':
			substack_id = resource.get("PhysicalResourceId", None)
			if substack_id is not None:
				resources.extend(get_stack_resources(substack_id))
	return resources

def set_tags(template):
	""" AWS limits us to 10 """
	tags = [
		{ "Key": "created-by",  "Value": "ramble" },
		{ "Key": "pcf-version", "Value": template["Metadata"]["pcf-version"] }
	]
	return tags

def get_tag(stack, key):
	tags = stack["Tags"]
	tag = next((t for t in tags if t["Key"] == key), None)
	return tag["Value"] if tag is not None else None

def get_output(stack, key):
	outputs = stack["Outputs"]
	output = next((o for o in outputs if o["OutputKey"] == key), None)
	return output["OutputValue"] if output is not None else None

def is_ramble_stack(stack):
	return get_tag(stack, "created-by") == "ramble"

def get_parameters(template):
	parameters = []
	for key in template["Parameters"]:
		value = None
		if template["Parameters"][key].get("Default", None) is not None:
			value = config.get('aws', friendly_name(key), None)
		else:
			value = config.get('aws', friendly_name(key))
		if value is not None:
			parameters.append({
				"ParameterKey": key,
				"ParameterValue": config.get('aws', friendly_name(key)),
				"UsePreviousValue": False
				})
	return parameters

""" Completely unnecessary functions but some of the name choices offend my sensibilities """

def friendly_name(oldname):
	newname = ""
	oldname = oldname.lstrip('0123456789') + "-"
	hasdash = True
	for i in range(len(oldname) - 1):
		c1 = oldname[i]
		c2 = oldname[i+1]
		if c1.isupper() and c2.islower() and not hasdash:
			newname += '-' + c1.lower()
		elif c1.islower() and c2.isupper():
			newname += c1 + '-'
			hasdash = True
		else:
			newname += c1.lower()
			hasdash = False
	return newname

def friendly_status(status):
	return {
		"CREATE_COMPLETE":    "Created",
		"CREATE_IN_PROGRESS": "Creating",
		"CREATE_FAILED":      "Partial",
		"DELETE_COMPLETE":    "Deleted",
		"DELETE_IN_PROGRESS": "Deleting",
		"DELETE_FAILED":      "Failed to Delete",
		"UPDATE_COMPLETE":    "Updated",
		"UPDATE_IN_PROGRESS": "Updating",
		"UPDATE_FAILED":      "Failed to Update",
	}.get(status, "[" + status.lower().replace('_', '-') + "]")

def friendly_delta(delta):
	seconds = delta.seconds
	hours, remainder = divmod(seconds, 3600)
	minutes, seconds = divmod(remainder, 60)
	return '%02d:%02d:%02d' % (hours, minutes, seconds)

""" CloudFormation CLI exercising CloudFormation API """

def list_stacks_cmd(argv):
	stack_pattern = argv[1] if len(argv) > 1 else ""
	stacks = list_stacks(stack_pattern)
	stacks = sorted(stacks, key=lambda stack: stack["StackName"])
	print "\n".join([s["StackName"] for s in stacks])

def list_resources_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = select_stack(stack_name)
	resources = get_stack_resources(stack["StackId"])
	print "\n".join([friendly_status(r["ResourceStatus"]) + " " + r["LogicalResourceId"] for r in resources])

def create_stack_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	release = argv[2] if len(argv) > 2 else None
	template = download_template(release, verbose=True)
	create_stack(template, stack_name, verbose=True)

def delete_stack_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = select_stack(stack_name)
	delete_stack(stack, verbose=True)

def show_outputs_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = select_stack(stack_name)
	outputs = stack["Outputs"]
	print "\n".join([o["OutputKey"] + ": " + o["OutputValue"] for o in outputs])

def show_template_cmd(argv):
	release = argv[1] if len(argv) > 1 else None
	template = download_template(release)
	print json.dumps(template, indent=4)

commands = {
	"stacks":       { "func": list_stacks_cmd,    "usage": "stacks [<stack-name>]" },
	"create-stack": { "func": create_stack_cmd,   "usage": "create-stack <stack-name> [<release>]" },
	"delete-stack": { "func": delete_stack_cmd,   "usage": "delete-stack <stack-name>" },
	"resources":    { "func": list_resources_cmd, "usage": "resources <stack-name>" },
	"template":     { "func": show_template_cmd,  "usage": "template [<release>]" },
	"outputs":      { "func": show_outputs_cmd,   "usage": "outputs <stack-name>" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)
