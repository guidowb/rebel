#!/usr/bin/env python

import cli
import aws
import sys
import json

def remove_network_interface(interface):
	print "remove network interface", interface
	command = [
		'ec2',
		'delete-network-interface',
		'--network-interface-id', interface
	]
	aws.aws_cli(command)

def remove_vpc_network_interfaces(vpc):
	command = [
		'ec2',
		'describe-network-interfaces',
		'--filters', 'Name=vpc-id,Values=' + vpc
	]
	interfaces = json.load(aws_cli(command))["NetworkInterfaces"]
	for interface in interfaces:
		remove_network_interface(interface["NetworkInterfaceId"])

def remove_load_balancer(load_balancer):
	print "remove load-balancer", load_balancer
	command = [
		'elb',
		'delete-load-balancer',
		'--load-balancer-name', load_balancer
	]
	aws.aws_cli(command)

def remove_vpc_load_balancers(vpc):
	command = [
		'elb',
		'describe-load-balancers',
		'--filters', 'Name=vpc-id,Values=' + vpc
	]
	load_balancers = json.load(aws_cli(command))["LoadBalancerDescriptions"]
	for load_balancer in load_balancers:
		remove_load_balancer(load_balancer["LoadBalancerName"])

def remove_vpc(vpc):
	print "remove vpc", vpc
	remove_vpc_network_interfaces(vpc)
	remove_vpc_load_balancers(vpc)
	remove_vpc_instances(vpc)
	remove_vpc_subnets(vpc)
	remove_vpc_security_groups(vpc)
	command = [
		'ec2',
		'delete-vpc',
		'--vpc-id', vpc
	]
	aws.aws_cli(command)

def remove_all_vpcs():
	command = [
		'ec2',
		'describe-vpcs'
	]
	vpcs = json.load(aws_cli(command))["Vpcs"]
	for vpc in vpcs:
		if not vpc["IsDefault"]:
			remove_vpc(vpc["VpcId"])

def cleanup_all():
	remove_all_vpcs()
	remove_orphaned_volumes()
	remove_all_buckets()

commands = {
	"all":   { "func": cleanup_all,   "usage": "all" },
	"vpc":   { "func": cleanup_vpc,   "usage": "vpc <vpc-id>" },
	"stack": { "func": cleanup_stack, "usage": "stack <stack-name>" },
}

if __name__ == '__main__':
	try:
		cli.cli(sys.argv, commands)
	except subprocess.CalledProcessError as error:
		print 'Command failed with exit code', error.returncode
		print error.output
		sys.exit(error.returncode)
