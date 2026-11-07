
/* Host may choose a generated default map without replacing any authored map. */
static char siglum_default_map_path[1024];
static int siglum_default_map_locked = 0;
int siglum_configure_default_map(const char *path)
{
    int i = 0;
    if (siglum_default_map_locked || !path) return -1;
    while (i < 1023 && path[i]) i++;
    if (i == 1023 && path[i]) return -2;
    for (int j = 0; j <= i; j++) siglum_default_map_path[j] = path[j];
    return 0;
}
static const char *siglum_default_map_name(const char *fallback)
{
    siglum_default_map_locked = 1;
    return siglum_default_map_path[0] ? siglum_default_map_path : fallback;
}
