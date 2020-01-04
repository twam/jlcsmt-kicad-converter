#!/usr/bin/env python3
# coding=utf8
import sys
import csv
import re
import json
import os
from jlcsmt_library import Library, Part
from collections import OrderedDict
from difflib import SequenceMatcher
from termcolor import colored

def getCategoryFromName(name):
    match = re.match(r"([A-Z])[0-9]+", name)
    if match:
        designator = match.group(1)
        # Mapping according to KLC, S6.1 (http://kicad-pcb.org/libraries/klc/)
        if designator == "R":
            return "Resistor"
        elif designator == "C":
            return "Capacitor"
        elif designator == "L":
            return "Inductor"
        elif designator == "Q":
            return "Transistor"
        elif designator == "U":
            return "Integrated Circuit"
    else:
        return "Unknown"

def remapValue(value, names):
    value_remap = {
        'Resistor': {
            "100k": "100KΩ (1003) ±1%",
            "22k": "22KΩ (2202) ±1%",
            "10k": "10KΩ (1002) ±1%"
        }
    }

    firstName = names.split(',',1)[0]
    category = getCategoryFromName(firstName)

    if (category in value_remap) and (value in value_remap[category]):
        return value_remap[category][value]

    if category == "Resistor":
        value = re.sub(r"^(?P<integer>[0-9]+)(?P<prefix>[kKmM])(?P<decimal>[0-9]*)$",
            lambda x: x.group("integer") + ("." + x.group("decimal") if (x.group("decimal") != "") else "") + {'k': 'K', None: ""}.get(x.group("prefix"), x.group("prefix")) + "Ω",
            value)

    return value

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

def readKicadBom(filename):
    items = []

    with open(filename, "r") as file:
        reader = csv.DictReader(file, delimiter=';')
        for row in reader:
            item = dict(row)
            # Set mapped entries to 0
            item['jlcsmt_pn'] = None
            item['jlcsmt_type'] = None
            item['jlcsmt_footprint'] = None
            item['jlcsmt_comment'] = None
            items.append(item)

    return items

def writeJlcsmtBom(filename, bom):
    with open(filename, "w") as file:

        ordered_fieldnames = OrderedDict([('Comment',None),('Designator',None),('Footprint',None),('LCSC Part #',None),('LCSC Part Type',None)])
        writer = csv.DictWriter(file, delimiter=';', quoting=csv.QUOTE_NONNUMERIC, fieldnames=ordered_fieldnames)
        writer.writeheader()

        for item in bom:
            if (item['jlcsmt_pn'] != None) and (item['jlcsmt_type'] != None) and (item['jlcsmt_footprint'] != None) and (item['jlcsmt_comment'] != None):
                writer.writerow({'Comment': item['jlcsmt_comment'], 'Designator': item['Designator'], 'Footprint': item['jlcsmt_footprint'], 'LCSC Part #': item['jlcsmt_pn'], 'LCSC Part Type': item['jlcsmt_type']})
            else:
                print("No match for {designator} with '{designation}' in package '{package}'.".format(
                    designator=item['Designator'],
                    designation=item['Designation'],
                    package=item['Package']))

def mapToJlcsmt(mappingTable, bom, library):
    if not "parts" in mappingTable:
        print("Missing 'parts' in mappingTable")
        return

    for item in bom:
        match = re.match(r"^([A-Z]+)[0-9]+.*", item['Designator'])
        if match:
            designator = match.group(1)
        else:
            continue

        if not designator in mappingTable["parts"]:
            continue

        if not item['Package'] in mappingTable["parts"][designator]:
            continue

        if not item['Designation'] in mappingTable["parts"][designator][item['Package']]:
            continue

        pn = mappingTable["parts"][designator][item['Package']][item['Designation']]
        part = library.parts[pn]

        item['jlcsmt_pn'] = pn
        item['jlcsmt_type'] = part.type
        item['jlcsmt_footprint'] = part.package
        item['jlcsmt_comment'] = part.comment



kicadBom = readKicadBom(sys.argv[1])

partlibname = sys.argv[3]
partlib = Library(partlibname)

with open(os.path.join(os.path.dirname(sys.argv[0]), 'remap.json'), "r") as file:
    mappingTable = json.load(file)

mapToJlcsmt(mappingTable, kicadBom, partlib)

if (len(sys.argv) > 3):
    # partlibname = sys.argv[3]
    # partlib = Library(partlibname)

    #{'Comment': '1M', 'Layer': 'TopLayer', 'Description': 'Resistor 1', 'Footprint Description': 'Chip Resistor, Body 1.6x0.8mm, IPC Medium Density', 'Designator': 'R33', 'ComponentKind': 'Standard', 'Ref-X(mm)': '291.604', 'Height(mm)': '0.600', 'Ref-Y(mm)': '79.777', 'Variation': 'Fitted', 'Pad-X(mm)': '291.604', 'Footprint': 'R-0603-M', 'Center-Y(mm)': '79.777', 'Pad-Y(mm)': '80.577', 'Rotation': '270', 'Center-X(mm)': '291.604'}
    print("{name:20.20s} {value:20.20s} {package:20.20s} {package_mapped:20.20s} ".format(
        name='Designator', value='Value', package='Package', package_mapped='Package (mapped)'
        ))
    for item in kicadBom:
        name, value, package, num = [item['Designator'], item['Designation'], item['Package'], item['Quantity']]

        package_mapped = mappingTable['packages'].get(package, package)

        print("{name:20.20s} {value:20.20s} {package:20.20s} {package_mapped:20.20s} ".format(
            name=name, value=value, package=package, package_mapped=package_mapped
            ))

        if item['jlcsmt_pn'] == None:

            #print("########    Part " + str(value) + " in " + str(package) + "   #########")
            lcsc_partnr = None
            lcsc_parttype = None
            partnrDic = {}
            valueDir = {}

            for lib_package, lib_package_parts in partlib.packages.items():

            # for part in partlib:
            #     lib_partnr, lib_value, lib_package, lib_parttype, lib_cat  = [part['Part #'], part['Comment'], part['Package'], part['Type'], part['Category']]
                if (similar(package_mapped, lib_package) > 0.75):
                    for lib_partnr in lib_package_parts:
                        search_coeff = 0
                        lib_part = partlib.parts[lib_partnr]
                        lib_value = lib_part.comment
                        lib_parttype = lib_part.type
                        lib_cat = lib_part.category

                        if value in lib_value.lower() or lib_value.lower() in value:
                            search_coeff += 1.0 # prefer exactly matching parts
                        if "Basic" in lib_parttype:
                            search_coeff += 0.2 # prefer "Basic" components

                        if "_R" in package_mapped:# or ("_C" in package and "Capacitor" in lib_cat):
                            if "Resistor" in lib_cat: # improve results for resistors
                                partnrDic.update({str(lib_partnr) : (similar(value, lib_value) + search_coeff)})
                                valueDir.update({str(lib_partnr) : (str(lib_value) + str(", ") + str(lib_parttype))})
                        else:
                            partnrDic.update({str(lib_partnr) : (similar(value, lib_value) + search_coeff)})
                            valueDir.update({str(lib_partnr) : (str(lib_value) + str(", ") + str(lib_parttype))})

            found = len(partnrDic)
            if (found > 0):
                #print(colored("Most likely:", "yellow"))
                for i in range(min(found, 5)):
                    maximum = max(partnrDic, key=partnrDic.get)

                    # if (partnrDic[maximum] > 2.0):
                    #     print(valueDir[maximum] + ", " + str(int((partnrDic[maximum] - 2.0) * 100)) + "%:", end='')
                    # elif (partnrDic[maximum] > 1.0 and partnrDic[maximum] < 2.0):
                    #     print(valueDir[maximum] + ", " + str(int((partnrDic[maximum] - 1.0) * 100)) + "%:", end='')
                    # else:
                    #     print(valueDir[maximum] + ", " + str(int(partnrDic[maximum] * 100)) + "%:", end='')
                    # print("   {0:s} {1:5.2f}   ".format(valueDir[maximum], partnrDic[maximum]), end='')
                    # print(str(maximum))

                    lib_part = partlib.parts[maximum]

                    print(colored("  {value:20.20s} {type:20.20s} {package:20.20s} {manufacturer:20.20s} {mpn:20.20s} {category:20.20s} {pn:20.20s} {coeff:>6.2f} %  ".format(
                        pn=lib_part.pn,
                        value=lib_part.comment,
                        type=lib_part.type,
                        package=lib_part.package,
                        mpn=lib_part.mpn,
                        manufacturer=lib_part.manufacturer,
                        category=lib_part.category,
                        coeff=partnrDic[maximum]*100
                        ), "yellow"))

                    del valueDir[maximum]
                    del partnrDic[maximum]
            else:
                print(colored("   No components with package '{package}' found.".format(package = package_mapped), "red"))
        else:
            lib_part = partlib.parts[item['jlcsmt_pn']]
            print(colored("  {value:20.20s} {type:20.20s} {package:20.20s} {manufacturer:20.20s} {mpn:20.20s} {category:20.20s} {pn:20.20s} ".format(
                pn=lib_part.pn,
                value=lib_part.comment,
                type=lib_part.type,
                package=lib_part.package,
                mpn=lib_part.mpn,
                manufacturer=lib_part.manufacturer,
                category=lib_part.category,
                ), "green"))

writeJlcsmtBom(sys.argv[2], kicadBom)

sys.exit(1)
