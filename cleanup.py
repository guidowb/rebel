#!/usr/bin/env python

import cli
import aws as aws_module
import sys
import json

def aws(argv):
	try:
		return json.loads(aws_module.aws_cli_verbose(argv))
	except ValueError:
		return None

def remove_network_interface(interface):
	print "remove network interface", interface
	command = [
		'ec2',
		'delete-network-interface',
		'--network-interface-id', interface
	]
	aws(command)

def remove_vpc_network_interfaces(vpc):
	command = [
		'ec2',
		'describe-network-interfaces',
		'--filters', 'Name=vpc-id,Values=' + vpc
	]
	interfaces = aws(command)["NetworkInterfaces"]
	for interface in interfaces:
		remove_network_interface(interface["NetworkInterfaceId"])

def remove_load_balancer(load_balancer):
	print "remove load-balancer", load_balancer
	command = [
		'elb',
		'delete-load-balancer',
		'--load-balancer-name', load_balancer
	]
	aws(command)

def remove_vpc_load_balancers(vpc):
	command = [
		'elb',
		'describe-load-balancers',
	]
	load_balancers = aws(command)["LoadBalancerDescriptions"]
	load_balancers = [elb for elb in load_balancers if elb["VPCId"] == vpc]
	for load_balancer in load_balancers:
		remove_load_balancer(load_balancer["LoadBalancerName"])

def remove_instance(instance):
	print "remove instance", instance
	command = [
		'ec2',
		'terminate-instances',
		'--instance-ids', instance
	]
	aws(command)

def remove_vpc_instances(vpc):
	command = [
		'ec2',
		'describe-instances',
		'--filters', 'Name=vpc-id,Values=' + vpc
	]
	reservations = aws(command)["Reservations"]
	for reservation in reservations:
		instances = reservation["Instances"]
		for instance in instances:
			remove_instance(instance["InstanceId"])

def remove_subnet(subnet):
	print "remove subnet", subnet
	command = [
		'ec2',
		'delete-subnet',
		'--subnet-id', subnet
	]
	aws(command)

def remove_vpc_subnets(vpc):
	command = [
		'ec2',
		'describe-subnets',
		'--filters', 'Name=vpc-id,Values=' + vpc
	]
	subnets = aws(command)["Subnets"]
	for subnet in subnets:
		remove_subnet(subnet["SubnetId"])

def remove_security_group(group):
	print "remove security-group", group
	command = [
		'ec2',
		'delete-security-group',
		'--group-id', group
	]
	aws(command)

def remove_vpc_security_groups(vpc):
	command = [
		'ec2',
		'describe-security-groups',
		'--filters', 'Name=vpc-id,Values=' + vpc
	]
	groups = aws(command)["SecurityGroups"]
	groups = [ group for group in groups if group["GroupName"] != "default" ]
	for group in groups:
		remove_security_group(group["GroupId"])

def remove_route_table(table):
	print "remove route-table", table
	command = [
		'ec2',
		'delete-route-table',
		'--route-table-id', table
	]
	aws(command)

def remove_vpc_route_tables(vpc):
	command = [
		'ec2',
		'describe-route-tables',
		'--filters', 'Name=vpc-id,Values=' + vpc
	]
	tables = aws(command)["RouteTables"]
	tables = [ table for table in tables if len(table["Associations"]) == 0 ]
	for table in tables:
		remove_route_table(table["RouteTableId"])

def detach_internet_gateway(gateway, vpc):
	print "detach internet-gateway", gateway
	command = [
		'ec2',
		'detach-internet-gateway',
		'--internet-gateway-id', gateway,
		'--vpc-id', vpc
	]
	aws(command)

def detach_vpc_internet_gateways(vpc):
	command = [
		'ec2',
		'describe-internet-gateways',
		'--filters', 'Name=attachment.vpc-id,Values=' + vpc
	]
	gateways = aws(command)["InternetGateways"]
	for gateway in gateways:
		detach_internet_gateway(gateway["InternetGatewayId"], vpc)

def remove_rds_instance(instance):
	print "remove rds-instance", instance
	command = [
		'rds',
		'delete-db-instance',
		'--db-instance-identifier', instance,
		'--skip-final-snapshot'
	]
	aws(command)
	command = [
		'rds',
		'wait',
		'db-instance-deleted',
		'--db-instance-identifier', instance
	]
	aws(command)

def remove_rds_subnet_group(group):
	print "remove rds-subnet-group", group
	command = [
		'rds',
		'delete-db-subnet-group',
		'--db-subnet-group-name', group
	]
	aws(command)

def remove_vpc_rds_instances(vpc):
	command = [
		'rds',
		'describe-db-instances',
	]
	instances = aws(command)["DBInstances"]
	instances = [db for db in instances if db["DBSubnetGroup"]["VpcId"] == vpc]
	for instance in instances:
		remove_rds_instance(instance["DBInstanceIdentifier"])
		remove_rds_subnet_group(instance["DBSubnetGroup"]["DBSubnetGroupName"])

def remove_vpc(vpc):
	print "remove vpc", vpc, "dependencies"
	remove_vpc_load_balancers(vpc)
	remove_vpc_instances(vpc)
	remove_vpc_rds_instances(vpc)
	remove_vpc_network_interfaces(vpc)
	remove_vpc_subnets(vpc)
	remove_vpc_security_groups(vpc)
	remove_vpc_route_tables(vpc)
	detach_vpc_internet_gateways(vpc)
	print "remove vpc", vpc
	command = [
		'ec2',
		'delete-vpc',
		'--vpc-id', vpc
	]
	aws(command)

def remove_all_vpcs():
	command = [
		'ec2',
		'describe-vpcs'
	]
	vpcs = aws(command)["Vpcs"]
	for vpc in vpcs:
		if not vpc["IsDefault"]:
			remove_vpc(vpc["VpcId"])

def cleanup_all(argv):
	remove_all_vpcs()
	remove_orphaned_volumes()
	remove_all_buckets()

def cleanup_vpc(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	vpc = argv[1]
	remove_vpc(vpc)

def cleanup_stack(argv):
	TBD

commands = {
	"all":   { "func": cleanup_all,   "usage": "all" },
	"vpc":   { "func": cleanup_vpc,   "usage": "vpc <vpc-id>" },
	"stack": { "func": cleanup_stack, "usage": "stack <stack-name>" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)

