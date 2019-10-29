from lib.correction_functions import get_sectoral_profiles
from lib.spatial_functions import *


def generate_sites_from_shapefile(paths, param):
    """
    This function reads the geodataframe of the sites and extracts their respective names and areas, as well as the coordinates
    of their centroids. It adds assumptions about other attributes and saves the output in a CSV file.
    
    :param paths: Dictionary including the paths to the rasters *LAND*, *EEZ*, and to the output *sites_sub*.
    :type paths: dict
    :param param: Dictionary including the geodataframe of regions, and parameters defining the resolution, the coordinates of the scope, and the georeference dictionary.
    :type param: dict
    
    :return: The CSV file with the sites is saved directly in the desired path, along with the corresponding metadata in a JSON file.
    """
    timecheck("Start")

    # Initialize region masking parameters
    Crd_all = param["Crd_all"]
    GeoRef = param["GeoRef"]
    res_desired = param["res_desired"]
    nRegions = param["nRegions_sub"]
    regions_shp = param["regions_sub"]

    # Initialize dataframe
    regions = pd.DataFrame(
        0,
        index=range(0, nRegions),
        columns=[
            "Name",
            "Index_shapefile",
            "Area_m2",
            "Longitude",
            "Latitude",
            "slacknode",
            "syncarea",
            "ctrarea",
            "primpos",
            "primneg",
            "secpos",
            "secneg",
            "terpos",
            "terneg",
        ],
    )

    # Read masks
    with rasterio.open(paths["LAND"]) as src:
        A_land = src.read(1)
        A_land = np.flipud(A_land).astype(int)
    with rasterio.open(paths["EEZ"]) as src:
        A_sea = src.read(1)
        A_sea = np.flipud(A_sea).astype(int)

    status = 0
    for reg in range(0, nRegions):
        # Display Progress
        status += 1
        display_progress("Generating sites ", (nRegions, status))

        # Compute region_mask
        A_region_extended = calc_region(regions_shp.loc[reg], Crd_all, res_desired, GeoRef)

        # Get name of region
        if np.nansum(A_region_extended * A_land) > np.nansum(A_region_extended * A_sea):
            regions.loc[reg, "Name"] = regions_shp.loc[reg]["NAME_SHORT"]
        else:
            regions.loc[reg, "Name"] = regions_shp.loc[reg]["NAME_SHORT"] + "_offshore"

        # Calculate longitude and latitude of centroids
        regions.loc[reg, "Longitude"] = regions_shp.geometry.centroid.loc[reg].x
        regions.loc[reg, "Latitude"] = regions_shp.geometry.centroid.loc[reg].y

    # Calculate area using Lambert Cylindrical Equal Area EPSG:9835
    regions_shp = regions_shp.to_crs("+proj=cea")
    regions["Area_m2"] = regions_shp.geometry.area
    regions_shp = regions_shp.to_crs({"init": "epsg:4326"})

    # Get original index in shapefile
    regions["Index_shapefile"] = regions_shp["original_index"]

    # Assign slack node
    regions["slacknode"] = 0
    regions.loc[0, "slacknode"] = 1

    # Define synchronous areas and control areas
    regions["syncharea"] = 1
    regions["ctrarea"] = 1

    # Define reserves
    regions["primpos"] = 0
    regions["primneg"] = 0
    regions["secpos"] = 0
    regions["secneg"] = 0
    regions["terpos"] = 0
    regions["terneg"] = 0

    # Export model-independent list of regions
    regions.to_csv(paths["sites_sub"], index=False, sep=";", decimal=",")
    create_json(
        paths["sites_sub"],
        param,
        ["region_name", "subregions_name", "Crd_all", "res_desired", "GeoRef"],
        paths,
        ["LAND", "EEZ", "spatial_scope", "subregions"],
    )
    timecheck("End")


# def generate_intermittent_supply_timeseries(paths, param):
# '''
# description
# '''
# timecheck('Start')
# Timeseries = None

# # Loop over the technologies understudy
# for tech in param["technology"]:
# # Read coefs
# if os.path.isfile(paths["reg_coef"][tech]):
# Coef = pd.read_csv(paths["reg_coef"][tech], sep=';', decimal=',', index_col=[0])
# else:
# print("No regression Coefficients found for " + tech)
# continue

# # Extract hub heights and find the required TS
# hub_heights = pd.Series(Coef.columns).str.slice(3).unique()
# regions = pd.Series(Coef.columns).str.slice(0, 2).unique()
# quantiles = pd.Series(Coef.index)

# # Read the timeseries
# TS = {}
# hh = ''
# paths = ts_paths(hub_heights, tech, paths)
# for height in hub_heights:
# TS[height] = pd.read_csv(paths["raw_TS"][tech][height],
# sep=';', decimal=',', header=[0, 1], index_col=[0], dtype=np.float)

# # Prepare Dataframe to be filled
# TS_tech = pd.DataFrame(np.zeros((8760, len(regions))), columns=regions + '.' + tech)
# for reg in regions:
# for height in hub_heights:
# for quan in quantiles:
# if height != '':
# TS_tech[reg + '.' + tech] = TS_tech[reg + '.' + tech] + \
# (TS[height][reg, 'q' + str(quan)] * Coef[reg + '_' + height].loc[
# quan])
# else:
# TS_tech[reg + '.' + tech] = TS_tech[reg + '.' + tech] + \
# (TS[height][reg, 'q' + str(quan)] * Coef[reg].loc[quan])
# TS_tech.set_index(np.arange(1, 8761), inplace=True)
# if Timeseries is None:
# Timeseries = TS_tech.copy()
# else:
# Timeseries = pd.concat([Timeseries, TS_tech], axis=1)

# Timeseries.to_csv(paths["suplm_TS"], sep=';', decimal=',')
# print("File Saved: " + paths["suplm_TS"])
# Timeseries.to_csv(paths["urbs_suplm"], sep=';', decimal=',')
# print("File Saved: " + paths["urbs_suplm"])
# timecheck('End')


def generate_load_timeseries(paths, param):
    """
    This function reads the normalized sectoral standard load profiles, and the cleaned load time series for the countries in the scope.
    On one hand, it splits the time series into sectoral time series for each country. On the other hand, it determines the time series for each pixel of land use
    and for each person in the country, by assuming a relationship between sectors and land use types / population size. Finally, it aggregates the time series of the
    pixels that lie in the same subregions to obtain the time series for each desired subregion.
    
    :param paths: Dictionary containing the paths to the cleaned input, to the intermediate files and to the outputs.
    :type paths: dict
    :param param: Dictionary containing assumptions about the load, as well as the geodataframes for the countries and the subregions.
    :type param: dict
    
    :return: All the outputs are saved in CSV or SHP files in the defined paths, along with their metadata in JSON files.
    :rtype: None
    """

    timecheck("Start")

    # Sector land use allocation
    sector_lu = pd.read_csv(paths["assumptions_landuse"], index_col=0, sep=";", decimal=",")
    shared_sectors = set(sector_lu.columns).intersection(set(param["load"]["sectors"]))
    sector_lu = sector_lu[sorted(list(shared_sectors))]
    shared_sectors.add("RES")
    if not shared_sectors == set(param["load"]["sectors"]):
        warn(
            "The following sectors are not included in " + paths["assumptions_landuse"] + ": " + str(set(param["load"]["sectors"]) - shared_sectors),
            UserWarning,
        )

    landuse_types = [str(i) for i in sector_lu.index]
    param["landuse_types"] = landuse_types
    # Normalize the land use coefficients found in the assumptions table over each sector
    sector_lu = sector_lu.transpose().div(np.repeat(sector_lu.sum(axis=0)[:, None], len(sector_lu), axis=1))
    sec = [str(i) for i in sector_lu.index]

    # Share of sectors in electricity demand
    sec_share = pd.read_csv(paths["sector_shares_clean"], index_col=0, sep=";", decimal=",")

    # Create landuse and population maps, if they do not exist already
    if not os.path.exists(paths["LU"]):
        generate_landuse(paths, param)
    if not os.path.exists(paths["POP"]):
        generate_population(paths, param)

    # Count pixels of each land use type and create weighting factors for each country
    if not os.path.exists(paths["stats_countries"]):
        df = zonal_stats(param["regions_land"], {"Population": paths["POP"], "Landuse": paths["LU"]}, param)
        stat = param["regions_land"][["GID_0"]].rename(columns={"GID_0": "Country"}).join(df).set_index("Country")
        stat.to_csv(paths["stats_countries"], sep=";", decimal=",", index=True)
        create_json(paths["stats_countries"], param, ["region_name", "year", "load", "landuse_types"], paths, ["spatial_scope", "LU", "POP"])
    else:
        stat = pd.read_csv(paths["stats_countries"], sep=";", decimal=",", index_col=0)

    # Weighting by sector
    for s in sec:
        stat.loc[:, s] = np.dot(stat.loc[:, landuse_types], sector_lu.loc[s])

    if not (os.path.isfile(paths["df_sector"]) and os.path.isfile(paths["load_sector"]) and os.path.isfile(paths["load_landuse"])):

        # Get dataframe with cleaned timeseries for countries
        df_load_countries = pd.read_csv(paths["load_ts_clean"], sep=";", decimal=",")
        countries = param["regions_land"].rename(columns={"GID_0": "Country"})

        # Get sectoral normalized profiles
        profiles = get_sectoral_profiles(paths, param)

        # Prepare an empty table of the hourly load for the five sectors in each countries.
        df_sectors = pd.DataFrame(
            0,
            index=df_load_countries.index,
            columns=pd.MultiIndex.from_product([df_load_countries.columns.tolist(), param["load"]["sectors"]], names=["Country", "Sector"]),
        )

        # Copy the load profiles for each sector in the columns of each country, and multiply each sector by the share
        # defined in 'sec_share'. Note that at the moment the values are the same for all countries
        for c in df_load_countries.columns:
            for s in param["load"]["sectors"]:
                try:
                    df_sectors.loc[:, (c, s)] = profiles[s] * sec_share.loc[c, s]
                except KeyError:
                    df_sectors.loc[:, (c, s)] = profiles[s] * sec_share.loc[param["load"]["default_sec_shares"], s]

        # Normalize the load profiles over all sectors by the hour so that the sum of the loads of all sectors = 1
        # for each hour, then multiply with the actual hourly loads for each country
        df_scaling = df_sectors.groupby(level=0, axis=1).sum()
        for c in df_load_countries.columns:
            for s in sec + ["RES"]:
                df_sectors.loc[:, (c, s)] = df_sectors.loc[:, (c, s)] / df_scaling[c] * df_load_countries[c]

        # Calculate the yearly load per sector and country
        load_sector = df_sectors.sum(axis=0).rename("Load in MWh")

        # Prepare dataframe load_landuse, which calculates the hourly load for each land use unit in each country
        rows = landuse_types.copy()
        rows.append("RES")
        countries = sorted(list(set(stat.index.tolist()).intersection(set(df_load_countries.columns))))
        m_index = pd.MultiIndex.from_product([countries, rows], names=["Country", "Land use"])
        load_landuse = pd.DataFrame(0, index=m_index, columns=df_sectors.index)

        status = 0
        length = len(countries) * len(landuse_types) * len(sec)
        display_progress("Computing regions load", (length, status))
        for c in countries:  # Countries
            load_landuse.loc[c, "RES"] = load_landuse.loc[c, "RES"] + df_sectors[(c, "RES")] / stat.loc[c, "RES"]
            for lu in landuse_types:  # Land use types
                for s in sec:  # other sectors
                    load_landuse.loc[c, lu] = load_landuse.loc[c, lu] + sector_lu.loc[s, int(lu)] * df_sectors[(c, s)] / stat.loc[c, s]
                    status = status + 1
                    display_progress("Computing regions load", (length, status))

        # Save the data into HDF5 files for faster execution
        df_sectors.to_csv(paths["df_sector"], sep=";", decimal=",", index=False, header=True)
        create_json(paths["df_sector"], param, ["region_name", "year", "load"], paths, ["spatial_scope", "load_ts_clean"])
        print("Dataframe with time series for each country and sector saved: " + paths["df_sector"])
        load_sector.to_csv(paths["load_sector"], sep=";", decimal=",", index=True, header=True)
        create_json(paths["load_sector"], param, ["region_name", "year", "load"], paths, ["spatial_scope", "load_ts_clean"])
        print("Dataframe with yearly demand for each country and sector saved: " + paths["load_sector"])
        load_landuse.to_csv(paths["load_landuse"], sep=";", decimal=",", index=True)
        create_json(paths["load_landuse"], param, ["region_name", "year", "load", "landuse_types"], paths, ["spatial_scope", "load_ts_clean"])
        print("Dataframe with time series for each land use pixel saved: " + paths["load_landuse"])

    # Read CSV files
    df_sectors = pd.read_csv(paths["df_sector"], sep=";", decimal=",", header=[0, 1])
    load_sector = pd.read_csv(paths["load_sector"], sep=";", decimal=",", index_col=[0, 1])["Load in MWh"]
    load_landuse = pd.read_csv(paths["load_landuse"], sep=";", decimal=",", index_col=[0, 1])

    # Split subregions into country parts
    # (a subregion can overlap with many countries, but a country part belongs to only one country)
    reg_intersection = intersection_subregions_countries(paths, param)

    # Count number of pixels for each country part
    if not os.path.exists(paths["stats_country_parts"]):
        df = zonal_stats(reg_intersection, {"Population": paths["POP"], "Landuse": paths["LU"]}, param)
        stat_sub = reg_intersection[["NAME_SHORT"]].rename(columns={"NAME_SHORT": "Country_part"}).join(df).set_index("Country_part")
        stat_sub.to_csv(paths["stats_country_parts"], sep=";", decimal=",", index=True)
        create_json(
            paths["stats_country_parts"],
            param,
            ["region_name", "subregions_name", "landuse_types"],
            paths,
            ["spatial_scope", "LU", "POP", "Countries", "subregions"],
        )
    else:
        stat_sub = pd.read_csv(paths["stats_country_parts"], sep=";", decimal=",", index_col=0)

    # Add attributes for country/region
    stat_sub["Region"] = 0
    stat_sub["Country"] = 0
    for i in stat_sub.index:
        stat_sub.loc[i, ["Region", "Country"]] = i.split("_")
        if stat_sub.loc[i, "Country"] not in list(df_sectors.columns.get_level_values(0).unique()):
            stat_sub.drop(index=i, inplace=True)

    # Prepare dataframe to save the hourly load in each country part
    load_country_part = pd.DataFrame(0, index=stat_sub.index, columns=df_sectors.index.tolist() + ["Region", "Country"])
    load_country_part[["Region", "Country"]] = stat_sub[["Region", "Country"]]

    # Calculate the hourly load for each subregion
    status = 0
    length = len(load_country_part.index) * len(landuse_types)
    display_progress("Computing sub regions load:", (length, status))
    for cp in load_country_part.index:
        c = load_country_part.loc[cp, "Country"]
        # For residential:
        load_country_part.loc[cp, df_sectors.index.tolist()] = (
            load_country_part.loc[cp, df_sectors.index.tolist()] + stat_sub.loc[cp, "RES"] * load_landuse.loc[c, "RES"].to_numpy()
        )
        for lu in landuse_types:
            load_country_part.loc[cp, df_sectors.index.tolist()] = (
                load_country_part.loc[cp, df_sectors.index.tolist()] + stat_sub.loc[cp, lu] * load_landuse.loc[c, lu].to_numpy()
            )
            # Show progress
            status = status + 1
            display_progress("Computing load in country parts", (length, status))

    # Aggregate into subregions
    load_regions = load_country_part.groupby(["Region", "Country"]).sum()
    load_regions.reset_index(inplace=True)
    load_regions = load_regions.groupby(["Region"]).sum().T

    # Output
    load_regions.to_csv(paths["load_regions"], sep=";", decimal=",", index=True)
    create_json(
        paths["load_regions"],
        param,
        ["region_name", "subregions_name", "load", "landuse_types"],
        paths,
        ["spatial_scope", "LU", "POP", "Countries", "subregions"],
    )
    print("File saved: " + paths["load_regions"])

    timecheck("End")


def generate_transmission(paths, param):
    """
    This function reads the cleaned grid data and the shapefile of the subregions. It first determines the names of the regions
    connected by each line, *Region_start* and *Region_end*, and only keeps those between two different subregions. Then it estimates
    the length between the centroids of the regions and uses it to estimate the efficiency of the lines and their costs. Finally,
    it completes the missing attributes with general assumptions and saves the result in a CSV file.
    
    :param paths: Dictionary including the paths to *grid_cleaned*, *sites_sub*, *subregions*, *dict_lines_costs*, and the output *grid_completed*.
    :type param: dict
    :param param: Dictionary including the geodataframe of the subregions and grid-related assumptions.
    :type param: dict
    
    :return: The CSV file with the completed transmission data is saved directly in the desired path, along with its metadata in a JSON file.
    :rtype: None
    """
    timecheck("Start")

    # Read the geodataframe of subregions
    subregions = param["regions_sub"][["NAME_SHORT", "geometry"]]

    # Read the cleaned GridKit dataset
    grid_cleaned = pd.read_csv(paths["grid_cleaned"], header=0, sep=";", decimal=",")

    # Create point geometries
    grid_cleaned["V1"] = list(zip(grid_cleaned.V1_long, grid_cleaned.V1_lat))
    grid_cleaned["V1"] = grid_cleaned["V1"].apply(Point)
    grid_cleaned["V2"] = list(zip(grid_cleaned.V2_long, grid_cleaned.V2_lat))
    grid_cleaned["V2"] = grid_cleaned["V2"].apply(Point)

    # Create a dataframe for the start regions
    Region_start = gpd.GeoDataFrame(grid_cleaned[["l_id", "V1"]], geometry="V1", crs={"init": "epsg:4326"}).rename(columns={"V1": "geometry"})
    Region_start.crs = subregions.crs
    Region_start = gpd.sjoin(Region_start, subregions, how="left", op="intersects")[["NAME_SHORT"]].rename(columns={"NAME_SHORT": "Region_start"})

    # Create a dataframe for the end regions
    Region_end = gpd.GeoDataFrame(grid_cleaned[["l_id", "V2"]], geometry="V2", crs={"init": "epsg:4326"}).rename(columns={"V2": "geometry"})
    Region_end.crs = subregions.crs
    Region_end = gpd.sjoin(Region_end, subregions, how="left", op="intersects")[["NAME_SHORT"]].rename(columns={"NAME_SHORT": "Region_end"})

    # Join dataframes
    grid_regions = grid_cleaned.drop(["V1", "V2"], axis=1).join([Region_start, Region_end])

    intra = len(grid_regions.loc[(grid_regions["Region_start"] == grid_regions["Region_end"]) & ~(grid_regions["Region_start"].isnull())])
    extra = len(grid_regions.loc[grid_regions["Region_start"].isnull() | grid_regions["Region_end"].isnull()])
    inter = len(grid_regions) - intra - extra

    # Show numbers of intraregional, interregional and extraregional lines
    print("\nLinetypes : ")
    print((("intraregional", intra), ("interregional", inter), ("extraregional", extra)))

    # Remove intraregional and extraregional lines
    lines_concatenated = grid_regions.loc[
        (grid_regions["Region_start"] != grid_regions["Region_end"]) & ~(grid_regions["Region_start"].isnull() | grid_regions["Region_end"].isnull())
    ].copy()

    # Sort alphabetically and reindex
    lines_reversed = reverse_lines(lines_concatenated)
    lines_reversed.sort_values(["Region_start", "Region_end", "tr_type"], inplace=True)
    lines = lines_reversed.set_index(["Region_start", "Region_end", "tr_type"]).reset_index()
    lines.drop(["V1_long", "V1_lat", "V2_long", "V2_lat", "l_id"], axis=1, inplace=True)

    # Aggregate lines starting and ending in the same regions
    lines_grouped = lines.groupby(["Region_start", "Region_end", "tr_type"]).sum()

    # Reindex and rename columns
    lines_final = lines_grouped.reset_index().rename(columns={"Region_start": "Site In", "Region_end": "Site Out", "Capacity_MVA": "cap-up-therm"})
    lines_final["reactance"] = 1 / lines_final["Y_mho_ref_380kV"]

    # Create a dataframe to store all the possible combinations of pairs of 1st order neighbors
    df = pd.DataFrame(columns=["Site In", "Site Out"])
    zones = pd.read_csv(paths["sites_sub"], index_col=0, decimal=",", sep=";")
    weights = ps.lib.weights.Queen.from_shapefile(paths["subregions"])
    for z in range(len(zones)):
        for n in weights.neighbors[z]:
            if zones.iloc[z].name < zones.iloc[n].name:
                df = df.append(pd.DataFrame([[zones.iloc[z].name, zones.iloc[n].name]], columns=["Site In", "Site Out"]), ignore_index=True)

    # Join that dataframe with existing lines
    df["tr_type"] = "AC_OHL"
    df.set_index(["Site In", "Site Out", "tr_type"], inplace=True)
    df_joined = df.join(lines_final.set_index(["Site In", "Site Out", "tr_type"]), how="outer")

    # Fill empty values for capacity (inexistent lines)
    df_joined["cap-up-therm"].fillna(0, inplace=True)

    # Calculate length of lines based on distance between centroids
    df_joined.reset_index(drop=False, inplace=True)
    df_joined = df_joined.join(zones[["Longitude", "Latitude"]], on="Site In", rsuffix="_1", how="inner")
    df_joined = df_joined.join(zones[["Longitude", "Latitude"]], on="Site Out", rsuffix="_2", how="inner")
    df_joined["length"] = [
        distance.distance(
            tuple(df_joined.loc[i, ["Latitude", "Longitude"]].astype(float)), tuple(df_joined.loc[i, ["Latitude_2", "Longitude_2"]].astype(float))
        ).km
        for i in df_joined.index
    ]
    df_joined.drop(["Longitude", "Latitude", "Longitude_2", "Latitude_2"], axis=1, inplace=True)

    # Calculate efficiency
    dict_eff = param["grid"]["efficiency"]
    df_joined.reset_index(drop=True, inplace=True)
    df_joined["eff"] = 1
    for ind in df_joined.index:
        df_joined.loc[ind, "eff"] = dict_eff[df_joined.loc[ind, "tr_type"]] ** (df_joined.loc[ind, "length"] / 1000)

    # Calculate costs
    dict_lines_costs = pd.read_csv(paths["dict_lines_costs"], sep=";", decimal=",")
    dict_lines_costs.loc[dict_lines_costs["length_limit_km"] == "inf", "length_limit_km"] = np.inf
    df_joined["inv-cost"] = 0
    df_joined["fix-cost"] = 0
    df_joined["var-cost"] = 0
    for ind in df_joined.index:
        filter = (dict_lines_costs["tr_type"] == df_joined.loc[ind, "tr_type"]) & (dict_lines_costs["length_limit_km"] > df_joined.loc[ind, "length"])
        dict_costs = dict_lines_costs.loc[filter].sort_values(by=["length_limit_km"], axis=0).head(1)
        df_joined.loc[ind, "inv-cost"] = float(dict_costs["inv-cost-length"]) * df_joined.loc[ind, "length"] + float(dict_costs["inv-cost-fix"])
        df_joined.loc[ind, "fix-cost"] = float(dict_costs["fix-cost-length"]) * df_joined.loc[ind, "length"]

    # Add attributes
    df_completed = df_joined.copy()
    df_completed["Commodity"] = "Elec"
    df_completed["inst-cap"] = df_completed["cap-up-therm"]
    df_completed["act-lo"] = 0
    df_completed["act-up"] = 1
    df_completed["angle-up"] = 45
    df_completed["PSTmax"] = 0
    df_completed["cap-lo"] = 0
    df_completed["cap-up"] = df_completed["inst-cap"]
    df_completed["idx"] = df_completed.index + 1
    df_completed["wacc"] = param["grid"]["wacc"]
    df_completed["depreciation"] = param["grid"]["depreciation"]

    # Ouput
    df_completed.to_csv(paths["grid_completed"], sep=";", decimal=",", index=False)
    create_json(paths["grid_completed"], param, ["grid"], paths, ["transmission_lines", "grid_cleaned", "subregions", "dict_lines_costs"])
    print("File Saved: " + paths["grid_completed"])

    timecheck("End")


def generate_commodity(paths, param):
    """ documentation """
    timecheck("Start")

    assumptions = pd.read_excel(paths["assumptions"], sheet_name="Commodity")
    commodity = list(assumptions["Commodity"].unique())

    dict_price_instate = dict(zip(assumptions["Commodity"], assumptions["price mid"]))
    dict_price_outofstate = dict(zip(assumptions["Commodity"], assumptions["price out-of-state"]))
    dict_type_evrys = dict(zip(assumptions["Commodity"], assumptions["Type_evrys"]))
    dict_type_urbs = dict(zip(assumptions["Commodity"], assumptions["Type_urbs"]))
    dict_annual = dict(zip(assumptions["Commodity"], assumptions["annual"]))
    dict_co_max = dict(zip(assumptions["Commodity"], assumptions["max"]))
    dict_maxperstep = dict(zip(assumptions["Commodity"], assumptions["maxperstep"]))

    # Read the CSV containing the list of sites
    sites = pd.read_csv(paths["sites"], sep=";", decimal=",")

    # Read the CSV containing the annual load
    load = pd.read_csv(paths["annual_load"], index_col=["sit"])

    # Prepare output tables for evrys and urbs

    output_evrys = pd.DataFrame(columns=["Site", "Co", "price", "annual", "losses", "type"], dtype=np.float64)
    output_urbs = pd.DataFrame(columns=["Site", "Commodity", "Type", "price", "max", "maxperhour"])

    # Fill tables
    for s in sites["Site"]:
        for c in commodity:
            if c == "Elec":
                if s in load.index:
                    annual = load.loc[s][0]
                else:
                    annual = 0
            else:
                annual = dict_annual[c]
            if len(s) >= 2:
                output_evrys = output_evrys.append(
                    {"Site": s, "Co": c, "price": dict_price_instate[c], "annual": annual, "losses": 0, "type": dict_type_evrys[c]}, ignore_index=True
                )
                output_urbs = output_urbs.append(
                    {
                        "Site": s,
                        "Commodity": c,
                        "Type": dict_type_urbs[c],
                        "price": dict_price_instate[c],
                        "max": dict_co_max[c],
                        "maxperhour": dict_maxperstep[c],
                    },
                    ignore_index=True,
                )
            else:
                output_evrys = output_evrys.append(
                    {"Site": s, "Co": c, "price": dict_price_outofstate[c], "annual": annual, "losses": 0, "type": dict_type_evrys[c]},
                    ignore_index=True,
                )
                output_urbs = output_urbs.append(
                    {
                        "Site": s,
                        "Commodity": c,
                        "Type": dict_type_urbs[c],
                        "price": dict_price_outofstate[c],
                        "max": dict_co_max[c],
                        "maxperhour": dict_maxperstep[c],
                    },
                    ignore_index=True,
                )

    output_urbs.to_csv(paths["urbs_commodity"], index=False, sep=";", decimal=",")
    print("File Saved: " + paths["urbs_commodity"])

    output_evrys.to_csv(paths["evrys_commodity"], index=False, sep=";", decimal=",")
    print("File Saved: " + paths["evrys_commodity"])

    timecheck("End")


def generate_processes(paths, param):
    """ documentation """
    timecheck("Start")

    assumptions = pd.read_excel(paths["assumptions"], sheet_name="Process")
    # Only use the assumptions of that particular year
    assumptions = assumptions[assumptions["year"] == param["year"]]

    param["assumptions"] = read_assumptions_process(assumptions)

    depreciation = param["assumptions"]["depreciation"]
    on_off = param["assumptions"]["on_off"]

    # Get data from the shapefile
    pro_and_sto = gpd.read_file(paths["pro_sto"])

    # Split the storage from the processes
    process_raw = pro_and_sto[~pro_and_sto["CoIn"].isin(param["pro_sto"]["storage"])]
    print("Number of processes read: " + str(len(process_raw)))

    # Consider the lifetime of power plants
    process_current = filter_life_time(param, process_raw, depreciation)

    # Get Sites
    process_located, _ = get_sites(process_current, paths)
    print("Number of processes after duplicate removal: " + str(len(process_located)))

    # Reduce the number of processes by aggregating the small and must-run power plants
    process_compact = process_located.copy()
    for c in process_compact["CoIn"].unique():
        process_compact.loc[process_compact["CoIn"] == c, "on-off"] = on_off[c]

    # Select small processes and group them
    process_group = process_compact[(process_compact["inst-cap"] < param["pro_sto"]["agg_thres"]) | (process_compact["on-off"] == 0)]
    process_group = process_group.groupby(["Site", "CoIn"])

    # Define the attributes of the aggregates
    small_cap = pd.DataFrame(process_group["inst-cap"].sum())
    small_pro = pd.DataFrame(process_group["Pro"].first() + "_agg")
    small_coout = pd.DataFrame(process_group["CoOut"].first())
    small_year = pd.DataFrame(process_group["year"].min())

    # Aggregate the small processes
    process_small = small_cap.join([small_pro, small_coout, small_year]).reset_index()

    # Recombine big processes with the aggregated small ones
    process_compact = process_compact[(process_compact["inst-cap"] >= param["pro_sto"]["agg_thres"]) & (process_compact["on-off"] == 1)]
    process_compact = process_compact.append(process_small, ignore_index=True, sort=True)
    print("Number of compacted processes: " + str(len(process_compact)))

    # Process evrys, urbs
    evrys_process, urbs_process = format_process_model(process_compact, param)

    # Output
    urbs_process.to_csv(paths["urbs_process"], index=False, sep=";", decimal=",")
    print("File Saved: " + paths["urbs_process"])
    evrys_process.to_csv(paths["evrys_process"], index=False, sep=";", decimal=",", encoding="ascii")
    print("File Saved: " + paths["evrys_process"])

    timecheck("End")


def generate_storage(paths, param):
    """ documentation """
    timecheck("Start")

    # Read required assumptions
    assumptions = pd.read_excel(paths["assumptions"], sheet_name="Storage")

    # Only use the assumptions of that particular year
    assumptions = assumptions[assumptions["year"] == param["year"]]

    param["assumptions"] = read_assumptions_storage(assumptions)

    depreciation = param["assumptions"]["depreciation"]

    # Get data from the shapefile
    pro_and_sto = gpd.read_file(paths["pro_sto"])

    # Split the storages from the processes
    storage_raw = pro_and_sto[pro_and_sto["CoIn"].isin(param["pro_sto"]["storage"])]
    print("Number of storage units read: " + str(len(storage_raw)))

    # Consider lifetime of storage units
    storage_current = filter_life_time(param, storage_raw, depreciation)

    # Get sites
    storage_located, regions = get_sites(storage_current, paths)
    param["regions"] = regions
    print("Number of storage units after duplicate removal: " + str(len(storage_located)))

    # Reduce number of storage units by aggregating the small storage units
    storage_compact = storage_located.copy()

    # Select small processes and group them
    storage_group = storage_compact[storage_compact["inst-cap"] < param["pro_sto"]["agg_thres"]].groupby(["Site", "CoIn"])

    # Define the attributes of the aggregates
    small_cap = pd.DataFrame(storage_group["inst-cap"].sum())
    small_pro = pd.DataFrame(storage_group["Pro"].first() + "_agg")
    small_coout = pd.DataFrame(storage_group["CoOut"].first())
    small_year = pd.DataFrame(storage_group["year"].min())

    # Aggregate the small storage units
    storage_small = small_cap.join([small_pro, small_coout, small_year]).reset_index()

    # Recombine big storage units with the aggregated small ones
    storage_compact = storage_compact[storage_compact["inst-cap"] >= param["pro_sto"]["agg_thres"]]
    storage_compact = storage_compact.append(storage_small, ignore_index=True, sort=True)
    print("Number of compacted storage units: " + str(len(storage_compact)))

    # Take the raw storage table and group by tuple of sites and storage type
    storage_compact = storage_compact[["Site", "CoIn", "CoOut", "inst-cap"]].copy()
    storage_compact.rename(columns={"CoIn": "Sto", "CoOut": "Co"}, inplace=True)
    storage_group = storage_compact.groupby(["Site", "Sto"])

    # Define the attributes of the aggregates
    inst_cap0 = storage_group["inst-cap"].sum().rename("inst-cap-pi")

    co0 = storage_group["Co"].first()

    # Combine the list of series into a dataframe
    storage_compact = pd.DataFrame([inst_cap0, co0]).transpose().reset_index()

    # Storage evrys, urbs
    evrys_storage, urbs_storage = format_storage_model(storage_compact, param)

    # Output
    urbs_storage.to_csv(paths["urbs_storage"], index=False, sep=";", decimal=",")
    print("File Saved: " + paths["urbs_storage"])
    evrys_storage.to_csv(paths["evrys_storage"], index=False, sep=";", decimal=",", encoding="ascii")
    print("File Saved: " + paths["evrys_storage"])

    timecheck("End")


def generate_processes_and_storage_california(paths, param):
    timecheck("Start")
    Process = pd.read_excel(
        paths["database_Cal"],
        sheet_name="Operating",
        header=1,
        skipinitialspace=True,
        usecols=[0, 2, 5, 6, 7, 10, 11, 14, 17, 25, 26],
        dtype={"Entity ID": np.unicode_, "Plant ID": np.unicode_},
    )
    Process.rename(columns={"\nNameplate Capacity (MW)": "inst-cap", "Operating Year": "year"}, inplace=True)
    regions = gpd.read_file(paths["regions_SHP"])

    # Drop recently built plants (after the reference year),
    # non-operating plants, and plants outside the geographic scope
    Process = Process[
        (Process["year"] <= param["year"])
        & (Process["Status"].isin(param["pro_sto_Cal"]["status"]))
        & (Process["Plant State"].isin(param["pro_sto_Cal"]["states"]))
    ]

    for i in Process.index:
        # Define a unique ID for the processes
        Process.loc[i, "Pro"] = (
            Process.loc[i, "Plant State"]
            + "_"
            + Process.loc[i, "Entity ID"]
            + "_"
            + Process.loc[i, "Plant ID"]
            + "_"
            + Process.loc[i, "Generator ID"]
        )

        # Define the input commodity
        Process.loc[i, "CoIn"] = param["pro_sto_Cal"]["proc_dict"][Process.loc[i, "Energy Source Code"]]
        if Process.loc[i, "Technology"] == "Hydroelectric Pumped Storage":
            Process.loc[i, "CoIn"] = "PumSt"
        if (Process.loc[i, "CoIn"] == "Hydro_Small") and (Process.loc[i, "inst-cap"] > 30):
            Process.loc[i, "CoIn"] = "Hydro_Large"

        # Define the location of the process
        if Process.loc[i, "Pro"] == "CA_50045_56284_EPG":  # Manual correction
            Process.loc[i, "Site"] = "LAX"
        else:
            Process.loc[i, "Site"] = containing_polygon(Point(Process.loc[i, "Longitude"], Process.loc[i, "Latitude"]), regions)["NAME_SHORT"]

    # Define the output commodity
    Process["CoOut"] = "Elec"

    # Select columns to be used
    Process = Process[["Site", "Pro", "CoIn", "CoOut", "inst-cap", "year"]]
    print("Number of Entries: " + str(len(Process)))

    # Split the storages from the processes
    process_raw = Process[~Process["CoIn"].isin(param["pro_sto_Cal"]["storage"])]
    storage_raw = Process[Process["CoIn"].isin(param["pro_sto_Cal"]["storage"])]
    print("Number of Processes: " + str(len(process_raw)))
    print("Number of Storage systems: " + str(len(storage_raw)))

    # Processes
    # Reduce the number of processes by aggregating the small ones
    # Select small processes and group them
    process_group = process_raw[process_raw["inst-cap"] < 10].groupby(["Site", "CoIn"])
    # Define the attributes of the aggregates
    small_cap = pd.DataFrame(process_group["inst-cap"].sum())
    small_pro = pd.DataFrame(process_group["Pro"].first() + "_agg")
    small_coout = pd.DataFrame(process_group["CoOut"].first())
    small_year = pd.DataFrame(process_group["year"].min())
    # Aggregate the small processes
    process_small = small_cap.join([small_pro, small_coout, small_year]).reset_index()

    # Recombine big processes with the aggregated small ones
    process_compact = process_raw[process_raw["inst-cap"] >= 10].append(process_small, ignore_index=True)
    print("Number of Processes after agregation: " + str(len(process_compact)))
    evrys_process, urbs_process = format_process_model_California(process_compact, process_small, param)

    # Output
    urbs_process.to_csv(paths["urbs_process"], index=False, sep=";", decimal=",")
    print("File Saved: " + paths["urbs_process"])
    evrys_process.to_csv(paths["evrys_process"], index=False, sep=";", decimal=",", encoding="ascii")
    print("File Saved: " + paths["evrys_process"])

    # Storage Systems
    param["sites_evrys_unique"] = evrys_process.Sites.unique()
    evrys_storage, urbs_storage = format_storage_model_California(storage_raw, param)

    # Output
    urbs_storage.to_csv(paths["urbs_storage"], index=False, sep=";", decimal=",")
    print("File Saved: " + paths["urbs_storage"])
    evrys_storage.to_csv(paths["evrys_storage"], index=False, sep=";", decimal=",", encoding="ascii")
    print("File Saved: " + paths["evrys_storage"])

    timecheck("End")
