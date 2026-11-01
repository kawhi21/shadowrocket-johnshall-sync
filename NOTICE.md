# Rule data attribution

The generated routing lists are derived from Johnshall / Moshel's
[Shadowrocket-ADBlock-Rules-Forever](https://github.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever),
`release/sr_cnip_ad.conf`.

Upstream rule data is licensed under [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).
The derived rule data remains under that license.

Changes: extract routing rules only; remove settings, rewrites, MITM and comments;
split the original consecutive PROXY and REJECT blocks without changing their order;
remove policies from individual rules for RULE-SET use; normalize IPv6 CIDRs to IP-CIDR6.
CN direct and final proxy are retained in the local wrapper. Private proxy information is never an input.
