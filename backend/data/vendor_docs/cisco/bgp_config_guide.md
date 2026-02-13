# BGP Configuration Guide - Cisco IOS/IOS-XE

## Overview

BGP (Border Gateway Protocol) is the de-facto exterior gateway protocol (EGP) used to exchange routing information between autonomous systems (AS). Current version is BGP-4 (RFC 4271). BGP uses TCP port 179 for peering.

## Key Concepts

- **iBGP**: Peering within the same AS. Requires full mesh or route reflector/confederation.
- **eBGP**: Peering between different ASes. TTL=1 by default (directly connected).
- **AS Number**: 16-bit (1-65535) or 32-bit (up to 4294967295). Private range: 64512-65534.
- **Path Attributes**: AS_PATH, NEXT_HOP, LOCAL_PREF, MED, ORIGIN, COMMUNITY, etc.

## Basic BGP Configuration

### eBGP Peering

```
router bgp 65001
 bgp router-id 1.1.1.1
 neighbor 10.0.0.2 remote-as 65002
 neighbor 10.0.0.2 description ISP-UPSTREAM
 !
 address-family ipv4 unicast
  neighbor 10.0.0.2 activate
  network 192.168.0.0 mask 255.255.255.0
 exit-address-family
```

### iBGP Peering (Loopback)

```
router bgp 65001
 bgp router-id 1.1.1.1
 neighbor 2.2.2.2 remote-as 65001
 neighbor 2.2.2.2 update-source Loopback0
 !
 address-family ipv4 unicast
  neighbor 2.2.2.2 activate
  neighbor 2.2.2.2 next-hop-self
 exit-address-family
```

Always use `update-source Loopback0` for iBGP peers to ensure stability. Use `next-hop-self` so iBGP peers can reach eBGP-learned next-hops.

## BGP Authentication

```
router bgp 65001
 neighbor 10.0.0.2 password SECURE_BGP_KEY
```

BGP uses TCP MD5 signature (RFC 2385) for peer authentication. The password must match on both sides.

## BGP Route Reflector

Solves the iBGP full-mesh requirement. The route reflector (RR) reflects routes between clients.

```
! On Route Reflector:
router bgp 65001
 neighbor 2.2.2.2 remote-as 65001
 neighbor 2.2.2.2 route-reflector-client
 neighbor 3.3.3.3 remote-as 65001
 neighbor 3.3.3.3 route-reflector-client
```

### Route Reflector Design Rules

1. RR clients only peer with the RR (not full mesh)
2. RR reflects routes from client to client and to non-client
3. RR reflects routes from non-client to client only
4. Use cluster-id for redundant RRs: `bgp cluster-id 10.0.0.1`

## BGP Path Selection

BGP best path selection order:

1. Highest WEIGHT (Cisco-specific, local to router)
2. Highest LOCAL_PREF (propagated within AS)
3. Locally originated routes
4. Shortest AS_PATH
5. Lowest ORIGIN (IGP < EGP < Incomplete)
6. Lowest MED (metric, compared between same neighbor AS)
7. eBGP over iBGP
8. Lowest IGP metric to next-hop
9. Oldest eBGP route
10. Lowest neighbor router-id

## BGP Route Filtering

### Prefix List

```
ip prefix-list DENY-RFC1918 seq 5 deny 10.0.0.0/8 le 32
ip prefix-list DENY-RFC1918 seq 10 deny 172.16.0.0/12 le 32
ip prefix-list DENY-RFC1918 seq 15 deny 192.168.0.0/16 le 32
ip prefix-list DENY-RFC1918 seq 100 permit 0.0.0.0/0 le 32

router bgp 65001
 address-family ipv4 unicast
  neighbor 10.0.0.2 prefix-list DENY-RFC1918 in
```

### Route Map

```
route-map SET-LOCAL-PREF permit 10
 match ip address prefix-list CUSTOMER-ROUTES
 set local-preference 200

route-map SET-LOCAL-PREF permit 20

router bgp 65001
 address-family ipv4 unicast
  neighbor 10.0.0.2 route-map SET-LOCAL-PREF in
```

### AS Path Filter

```
ip as-path access-list 1 deny _65500_
ip as-path access-list 1 permit .*

router bgp 65001
 address-family ipv4 unicast
  neighbor 10.0.0.2 filter-list 1 in
```

## BGP Communities

### Standard Communities

```
route-map TAG-ROUTES permit 10
 set community 65001:100 additive

router bgp 65001
 address-family ipv4 unicast
  neighbor 10.0.0.2 send-community both
```

### Well-Known Communities

- `no-export`: Do not advertise to eBGP peers
- `no-advertise`: Do not advertise to any peer
- `local-as`: Do not advertise outside local AS (for confederations)

```
route-map NO-EXPORT permit 10
 set community no-export additive
```

## BGP Timers

Default timers: Keepalive=60s, Hold=180s.

```
router bgp 65001
 ! Global timers
 timers bgp 30 90

 ! Per-neighbor timers
 neighbor 10.0.0.2 timers 10 30
```

For fast convergence in data center environments:

```
neighbor 10.0.0.2 timers 3 9
neighbor 10.0.0.2 fall-over bfd
```

## BGP Troubleshooting Commands

```
show ip bgp summary
show ip bgp neighbors 10.0.0.2
show ip bgp
show ip bgp 192.168.1.0/24
show ip bgp neighbors 10.0.0.2 advertised-routes
show ip bgp neighbors 10.0.0.2 received-routes
show ip bgp neighbors 10.0.0.2 routes
debug ip bgp updates
debug ip bgp events
```

### Common Issues

1. **Neighbor stuck in IDLE**: TCP connectivity issue, check `ping`, firewall (TCP 179), and TTL
2. **Neighbor stuck in ACTIVE**: Remote side not configured, wrong IP, or password mismatch
3. **Neighbor stuck in OPENSENT**: Authentication failure or capability mismatch
4. **Routes not advertised**: Missing `network` statement, route not in RIB, or filtered by policy
5. **Next-hop unreachable**: Missing `next-hop-self` in iBGP, or no IGP route to next-hop

### eBGP Multihop

When eBGP peers are not directly connected:

```
neighbor 10.0.0.2 ebgp-multihop 2
```

Or for loopback peering:

```
neighbor 2.2.2.2 ebgp-multihop 2
neighbor 2.2.2.2 update-source Loopback0
```

## BGP Aggregate Routes

```
router bgp 65001
 address-family ipv4 unicast
  aggregate-address 10.0.0.0 255.255.0.0 summary-only
```

The `summary-only` keyword suppresses the more specific routes. Without it, both aggregate and specifics are advertised.

## BGP Graceful Restart

```
router bgp 65001
 bgp graceful-restart
 bgp graceful-restart restart-time 120
 bgp graceful-restart stalepath-time 360
```

Minimizes traffic disruption during BGP process restart.

## Best Practices

1. Always configure `bgp router-id` explicitly
2. Use loopback interfaces for iBGP peering with `update-source`
3. Apply `next-hop-self` on iBGP peers
4. Filter RFC 1918 and bogon routes from eBGP
5. Use MD5 authentication on all BGP sessions
6. Implement maximum-prefix limits: `neighbor 10.0.0.2 maximum-prefix 1000 80`
7. Use route reflectors instead of iBGP full mesh
8. Apply both inbound and outbound route policies
9. Enable BFD for fast failure detection: `neighbor 10.0.0.2 fall-over bfd`
10. Use soft reconfiguration for policy changes: `neighbor 10.0.0.2 soft-reconfiguration inbound`
