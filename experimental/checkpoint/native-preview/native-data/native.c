#include <unicode/udata.h>
#include <unicode/putil.h>
int siglum_icu_use_files(void) {
    UErrorCode status = U_ZERO_ERROR;
    u_setDataDirectory("/icu");
    udata_setFileAccess(UDATA_FILES_FIRST, &status);
    return status;
}
#include <unicode/unorm2.h>
#include <unicode/ustring.h>
#include <unicode/ucnv.h>
#include <unicode/ubrk.h>
int siglum_icu_probe(void) {
    UErrorCode error = U_ZERO_ERROR;
    UChar output[64];
    const UChar decomposed[] = {0x65,0x301};
    const UNormalizer2 *nfc = unorm2_getNFCInstance(&error);
    if (U_FAILURE(error)||!nfc) return 1;
    int n=unorm2_normalize(nfc,decomposed,2,output,64,&error);
    if (U_FAILURE(error)||n!=1||output[0]!=0xe9) return 2;
    const UChar capitals[] = {0x49,0x130};
    n=u_strToLower(output,64,capitals,2,"tr",&error);
    if (U_FAILURE(error)||n!=2||output[0]!=0x131||output[1]!=0x69) return 3;
    UConverter *converter=ucnv_open("windows-1251",&error);
    if (U_FAILURE(error)||!converter) return 4;
    const char encoded[]={ (char)0xdf };
    n=ucnv_toUChars(converter,output,64,encoded,1,&error);
    ucnv_close(converter);
    if (U_FAILURE(error)||n!=1||output[0]!=0x42f) return 5;
    const UChar thai[]={0xe20,0xe32,0xe29,0xe32,0xe44,0xe17,0xe22};
    UBreakIterator *iterator=ubrk_open(UBRK_LINE,"th",thai,7,&error);
    if (U_FAILURE(error)||!iterator) return 6;
    int first=ubrk_first(iterator),next=ubrk_next(iterator);
    ubrk_close(iterator);
    if (first!=0||next<=0||next>7) return 7;
    return 0;
}
