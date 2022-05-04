# Pre-defined sets for the Set Picking Dialog.
#
# Each entry is two lines. The first is the text that will be displayed
# and is the name of the Set and the second is the its ASL definition.
# Any line that begins with a '#' is ignored as a comment
#
# Note that it's not possible to have use any aliases (like "and" for "and")
# in the definitions in this file. 
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
a.ato 12, 30, 26, 27, 29, 11, 19, 20, 48, 24, 28, 79, 47, 78
#a.e Mg, Mn, Zn, Fe, Co, Cu, Na, K, Ca, Cd, Cr, Ni, Au, Ag, Pt
#
Fluorescent residues 
"fillres ( res.pt tyr or res.pt trp or res.pt phe ) "
# Cystine absorbs very weakly in this range
UV active residues (250-280nm)
"fillres ( res.pt tyr or res.pt trp or res.pt phe or (/S1-S1/ and res.pt cys)) "
#
UV active residues (210-230nm)
"fillres ( res.pt asp or res.pt glu or res.pt asn or res.pt gln or res.pt arg or res.pt his or res.pt cys ) "
#
Chymotrypsin restriction site 
"fillres (( a.pt c and res.pt tyr or res.pt phe or res.pt trp ) and not(withinbonds 1 a.pt n and res.pt pro)) "
#
Trypsin restriction site 
"fillres (( a.pt c and (res.pt arg, lys) ) and not(withinbonds 1 a.pt n and res.pt pro))"
#
V-8 restriction site 
"fillres (( a.pt c and (res.pt glu, asp) ) and not(withinbonds 1 a.pt n and res.pt pro))"
#
Cyanogen Bromide cleavage site  
"fillres (( a.pt c and (res.pt met) ) and not(withinbonds 1 a.pt n and res.pt pro))"
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
