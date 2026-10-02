/* Company media is supplied by the current workspace's catalog only. */
export const companyProductImage = (media, product) => media?.products?.[product?.name] || null;
export const companyProjects = (media, custom, platformProjects) => custom ? media?.projects || [] : platformProjects;
