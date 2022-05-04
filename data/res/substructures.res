# Pre-defined substructures for the Set Picking Dialog.
#
# Each entry is two lines. The first is the text that will be displayed in
# the list of substructures. The second is the actual substructure itself.
# Any line that begins with a '#' is ignored as a comment
#
Solvent
/H2-O3-H2/ or res.pt HOH or (res.pt SO4) or (res.pt CIT ) or (res.p ACT) or (res.p DMS) or (a.e Mg, Mn, Zn, Fe, Co, Cu, Na, K, Ca, Cd, Cr, Ni, Au, Ag, Pt) 
#
Water
/H2-O3-H2/ or res.pt HOH
# 
Sulfate
res.pt SO4
#
Citrate
res.pt CIT
#
Acetate
res.pt ACT
#
DMSO
res.pt DMS
#
Metals
a.e Mg, Mn, Zn, Fe, Co, Cu, Na, K, Ca, Cd, Cr, Ni, Au, Ag, Pt
#
Fluorescent residues 
"fillres ( res.pt tyr or res.pt trp or res.pt phe ) "
# Cystine absorbs very weakly in this range
UV active residues (250-280nm)
"fillres ( res.pt tyr or res.pt trp or res.pt phe or (/s1-s1/ and res.pt cys)) "
#
UV active residues (210-230nm)
"fillres ( res.pt asp or res.pt glu or res.pt asn or res.pt gln or res.pt arg or res.pt his or res.pt cys ) "
#
Chymotrypsin restriction site 
"fillres (( a.pt c & res.pt tyr or res.pt phe or res.pt trp ) & !(withinbonds 1 a.pt n & res.pt pro)) "
#
Trypsin restriction site 
"fillres (( a.pt c & (res.pt arg, lys) ) & !(withinbonds 1 a.pt n & res.pt pro))"
#
V-8 restriction site 
"fillres (( a.pt c & (res.pt glu, asp) ) & !(withinbonds 1 a.pt n & res.pt pro))"
#
Cyanogen Bromide cleavage site  
"fillres (( a.pt c & (res.pt met) ) & !(withinbonds 1 a.pt n & res.pt pro))"
#
Phosphate
/P0(-OM)(*O0)(*O0)(*O0)/
# 
Chloride (Cl-)
/Cm/
#
Three-membered rings
/00*00*00-1/
#
Four-membered rings
/00*00*00*00-1/
#
Five-membered rings
/00*00*00*00*00-1/
#
Six-membered rings
/00*00*00*00*00*00-1/
#
