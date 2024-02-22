from bungio.models import DestinyUser, DestinyComponentType


async def main(auth):
    destiny_profile = await DestinyUser(membership_id=auth.membership_id, membership_type=auth.membership_type).get_linked_profiles(get_all_memberships=True, auth=auth)
    destiny_profile = destiny_profile.profiles[0]

    profile_characters = await destiny_profile.get_profile(components=[DestinyComponentType.CHARACTERS], auth=auth)
    characters = profile_characters.characters.data
    for character in characters:
        await characters[character].fetch_manifest_information()
        print(f"Персонаж: {characters[character].manifest_class_hash.display_properties.name}")

        vendors = await characters[character].get_vendors(components=[DestinyComponentType.VENDORS, DestinyComponentType.VENDOR_SALES], filter=0, auth=auth)

        for vendor in vendors.vendors.data:
            await vendors.vendors.data[vendor].fetch_manifest_information()
            await vendors.sales.data[vendor].fetch_manifest_information()
            print(f"Вендор: {vendors.vendors.data[vendor].manifest_vendor_hash.display_properties.name}")
            for item in vendors.sales.data[vendor].sale_items:
                item_obj = vendors.sales.data[vendor].sale_items[item]
                await item_obj.fetch_manifest_information()
                print(f"Предмет: {item_obj.manifest_item_hash.display_properties.name}")
                for cost in item_obj.costs:
                    await cost.fetch_manifest_information()
                    print(f"Цена: {cost.manifest_item_hash.display_properties.name} - {cost.quantity}")
