#!/usr/bin/env python3
"""
process.py ingests a GeoLite2 CSV database and emits a compact bitset datastructure
to test for European IP addresses.
"""

# pylint: disable=invalid-name

import csv
import io
import os
import ipaddress
import struct
import zipfile


# TODO: update for Brexit?
EU_COUNTRIES = set(
    "AT BE BG CY CZ DE DK EE EL ES FI FR HR HU "
    "IE IT LT LU LV MT NL PL PT RO SE SI SK UK".split())

def get_euro_cidrs(path):
    f = zipfile.ZipFile(path)

    def load(suffix):
        entry = next(e for e in f.filelist if e.filename.endswith(suffix))
        contents = f.read(entry).decode('utf8')
        return csv.DictReader(io.StringIO(contents))

    ipv4 = load('IPv4.csv')
    ipv6 = load('IPv6.csv')
    locs = load('Locations-en.csv')
    version = os.path.dirname(f.filelist[0].filename).split('_')[1]

    eu_locs = set()
    for loc in locs:
        if loc['country_iso_code'] in EU_COUNTRIES:
            eu_locs.add(loc['geoname_id'])

    ipv4_cidrs = [row['network'] for row in ipv4 if row['geoname_id'] in eu_locs]
    ipv6_cidrs = [row['network'] for row in ipv6 if row['geoname_id'] in eu_locs]

    ipv4_cidrs.sort()
    ipv6_cidrs.sort()

    def collapse(cs):
        return list(ipaddress.collapse_addresses(ipaddress.ip_network(c) for c in cs))

    ipv4_collapsed = collapse(ipv4_cidrs)
    ipv6_collapsed = collapse(ipv6_cidrs)

    return ipv4_collapsed, ipv6_collapsed, version

def emit_simple(v4, v6, b4, b6):
    """
    Output ranges in a simple packed format-- binary address followed by CIDR width.
    """
    for n in v4:
        b4.write(n.network_address.packed)
        b4.write(struct.pack('B', n.prefixlen))
    for n in v6:
        b6.write(n.network_address.packed)
        b6.write(struct.pack('B', n.prefixlen))

def networks_to_ranges(nets):
    out = []
    for net in nets:
        out.append((int(net.network_address), int(net.broadcast_address)))
    return out

class Node:
    """
    Node represents an entry in a bitset DAG.

    Child pointers are eliminated by having two bitsets to indicate their presence:
    one indicates where child pointers are, and one indicates children that indicate
    "all bits are set".

    See https://dotat.at/prog/qp/blog-2015-10-04.html for more inspiration.

    Output structure:
        has_child   16b: whether it has a child pointer for each of 16 possible children
        set_child   16b: whether a child is all true (optimization-- has_child&set_child == 0)
        children    16b * bitcount(has_child): pointer to child entry, right shifted by 1.
    """

    def __init__(self, parent=None):
        self.addr = None
        self.children = [None] * 16
        self.parents = []
        if parent:
            self.parents.append(parent)

    def binary(self):
        has_child = sum(1 << n for n, child in enumerate(self.children)
                        if child and child.addr > 0)
        zero_children = sum(1 << n for n, child in enumerate(self.children)
                            if child and child.addr == 0)
        child_addrs = [c.addr >> 1 for c in self.children if c and c.addr > 0]
        # print(has_child, zero_children, child_addrs)
        return struct.pack('<HH%dH' % len(child_addrs), has_child, zero_children, *child_addrs)

    def size(self):
        return 4 + sum(2 if (c and c.parents) else 0 for c in self.children)
        # Alternative (worse) encodings:
        # set_child is actually new_child, indicating if a pointer is the same as the last one.
        # return 4 + 2 * len(set(self.children) - {None})
        # No set_child map, so zero pointer have to be included:
        # return 2 + sum(3 if c else 0 for c in self.children)

    # __hash__ and __eq__ allow for easy deduping
    def __hash__(self):
        return hash(tuple(id(x) for x in self.children))

    def __eq__(self, other):
        if not isinstance(self, other.__class__):
            return False
        return self.children == other.children

    def __str__(self):
        if self.addr is not None:
            return 'Node@%04d[%s]' % (
                self.addr, ",".join(str(c.addr) if c else '_' for c in self.children))
        return 'Node<%x>' % id(self)


def emit_bitdag(ranges, outfile, width):
    nodes = []
    def new_node(parent=None):
        n = Node(parent)
        nodes.append(n)
        return n

    root = new_node()  # children pointing to the root (a cycle) indicate that a node is true

    # set the nodes
    def make_nibbles(x):
        return [((x >> n) & 0xf) for n in range(width - 4, -1, -4)]

    def set_range(start, end):
        assert start <= end, (start, end)
        assert bin(start ^ end).rstrip('1') in ('0b', '0b0'), (hex(start), hex(end))

        node = root
        for a, b in zip(make_nibbles(start), make_nibbles(end)):
            if a == b:
                if node.children[a] is None:
                    node.children[a] = new_node(node)
                node = node.children[a]
            else:
                if a == 0 and b == 15:
                    # special case entire range set
                    parent = node.parents[0]
                    parent.children = [c if c is not node else root for c in parent.children]
                else:
                    for n in range(a, b + 1):
                        node.children[n] = root
                # print("%s %x %x %d %d" % (node, start, end, a, b))
                return

    for start, end in ranges:
        set_range(start, end)

    def dedupe():
        count_before = len(nodes)
        changed = True
        while changed:
            changed = False
            node_map = {}
            deduped = []
            for n, node in enumerate(nodes):
                if node not in node_map:
                    node_map[node] = node
                else:
                    changed = True
                    canonical = node_map[node]
                    for p in node.parents:
                        p.children = [c if c is not node else canonical for c in p.children]
                    canonical.parents.extend(node.parents)
                    deduped.append(n)
            # print("removed %d nodes!" % len(deduped))
            nodes[:] = [node for n, node in enumerate(nodes) if n not in deduped]
        print(count_before, "=>", len(nodes), "nodes for", len(ranges), "ranges")

    dedupe()

    def assign_addrs():
        cur = 0
        for node in nodes:
            node.addr = cur
            cur += node.size()
        total_size = cur
        print("total size:", total_size)
        assert total_size < 1 << 17, "ERROR: need 24-bit pointers!"

    assign_addrs()

    # for node in nodes: print(node, node.binary().hex())

    # validate
    for node in nodes:  # shouldn't have any unnecessary nodes like this
        assert node.children != [root] * 16, node

    def test(x, expected):
        # print("test %x %s" % (x, expected))
        node = root
        nibs = make_nibbles(x)
        for a in nibs:
            if not node.children[a]:
                assert not expected, (str(node), hex(x), nibs)
                return
            node = node.children[a]
            if node is root:
                assert expected, (str(node), hex(x), nibs)
                return

    for n, (start, end) in enumerate(ranges):
        if n == 0 or ranges[n-1][1] < start - 1:  # adjacency is possible
            test(start - 1, False)
        test(start, True)
        test((start + end) // 2, True)
        test(end, True)
        if n < len(ranges) - 1 and ranges[n+1][0] > end + 1:  # adjacency is possible
            test(end + 1, False)

    # emit
    for node in nodes:
        outfile.write(node.binary())


def main():
    try:
        v4 = [ipaddress.ip_network(l.strip()) for l in open('euro_v4.txt')]
        v6 = [ipaddress.ip_network(l.strip()) for l in open('euro_v6.txt')]
    except IOError:
        v4, v6, version = get_euro_cidrs('GeoLite2-Country-CSV.zip')
        with open('euro_v4.txt', 'w') as f:
            for c in v4:
                f.write('%s\n' % c)
        with open('euro_v6.txt', 'w') as f:
            for c in v6:
                f.write('%s\n' % c)
        with open('version.txt', 'w') as f:
            f.write(version + '\n')

    print("%d v4 ranges" % len(v4))
    print("%d v6 ranges" % len(v6))

    with open('euro_v4.bin', 'wb') as b4, open('euro_v6.bin', 'wb') as b6:
        emit_simple(v4, v6, b4, b6)

    v4_ranges = networks_to_ranges(v4)
    v6_ranges = networks_to_ranges(v6)

    with open('euro_v4.btr', 'wb') as b4:
        emit_bitdag(v4_ranges, b4, 32)
    with open('euro_v6.btr', 'wb') as b6:
        emit_bitdag(v6_ranges, b6, 128)

if __name__ == '__main__':
    main()
